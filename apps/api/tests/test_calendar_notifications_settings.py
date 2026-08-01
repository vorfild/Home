from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.services.notifications import generate_due_notifications

TEST_PASSWORD = f"Test-{secrets.token_urlsafe(12)}-7"


@pytest.fixture
def stage7_client() -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def setup(client: TestClient) -> str:
    response = client.post(
        "/api/v1/setup",
        json={
            "timezone": "Europe/Helsinki",
            "household_name": "Дом",
            "admin_name": "Алексей",
            "admin_login": "alexey",
            "admin_password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()["csrf_token"]


def test_child_keeps_critical_notification_rules_and_admin_controls_modules(
    stage7_client: tuple[TestClient, object],
) -> None:
    client = stage7_client[0]
    csrf = setup(client)
    child = client.post(
        "/api/v1/family/members",
        json={"name": "Миша", "login": "misha", "role": "child"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    modules = client.put(
        "/api/v1/settings/modules",
        json={
            "meters": False,
            "email": True,
            "shopping_prices": False,
            "maintenance_finances": True,
            "task_photos": True,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert modules.status_code == 200
    assert modules.json()["meters"] is False

    client.cookies.clear()
    child_auth = client.post(
        "/api/v1/auth/login",
        json={"login": "misha", "password": child["temporary_password"]},
    ).json()
    preferences = client.get("/api/v1/settings/preferences").json()
    changed = client.put(
        "/api/v1/settings/preferences",
        json={
            **preferences,
            "theme": "dark",
            "channels": {"in_app": False, "push": False, "email": False},
            "event_rules": {"task_due": False},
        },
        headers={"X-CSRF-Token": child_auth["csrf_token"]},
    )
    assert changed.status_code == 200
    assert changed.json()["theme"] == "dark"
    assert changed.json()["channels"]["in_app"] is True
    assert changed.json()["event_rules"]["task_due"] is True


def test_calendar_aggregates_sources_filters_and_moves_event(
    stage7_client: tuple[TestClient, object],
) -> None:
    client = stage7_client[0]
    csrf = setup(client)
    client.post(
        "/api/v1/tasks",
        json={
            "title": "Проверить дом",
            "due_at": "2026-08-05T10:00:00+03:00",
            "assignment_mode": "fixed",
            "assignee_ids": [client.get("/api/v1/auth/me").json()["user"]["id"]],
        },
        headers={"X-CSRF-Token": csrf},
    )
    shopping = client.post(
        "/api/v1/shopping/lists",
        json={"title": "Стройматериалы", "scheduled_at": "2026-08-06T18:00:00+03:00"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    node = client.post(
        "/api/v1/storage/nodes",
        json={"name": "Гараж"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    client.post(
        "/api/v1/storage/items",
        json={"name": "Краска", "node_id": node["id"], "review_at": "2026-08-07T12:00:00+03:00"},
        headers={"X-CSRF-Token": csrf},
    )
    equipment = client.post(
        "/api/v1/home/equipment",
        json={"name": "Насос", "warranty_until": "2026-08-08"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    client.post(
        "/api/v1/home/maintenance",
        json={
            "equipment_id": equipment["id"],
            "title": "Смазать насос",
            "interval_days": 90,
            "next_on": "2026-08-09",
        },
        headers={"X-CSRF-Token": csrf},
    )
    client.post(
        "/api/v1/home/meters",
        json={"meter_type": "Вода", "unit": "м³", "next_submission_on": "2026-08-10"},
        headers={"X-CSRF-Token": csrf},
    )

    response = client.get(
        "/api/v1/calendar?start=2026-08-01T00:00:00%2B03:00&end=2026-09-01T00:00:00%2B03:00"
    )
    assert response.status_code == 200
    assert {item["source_type"] for item in response.json()} == {
        "task",
        "shopping",
        "storage",
        "warranty",
        "maintenance",
        "meter",
    }
    filtered = client.get(
        "/api/v1/calendar?start=2026-08-01T00:00:00%2B03:00&end=2026-09-01T00:00:00%2B03:00&type=shopping"
    )
    assert len(filtered.json()) == 1
    moved = client.post(
        "/api/v1/calendar/move",
        json={
            "source_type": "shopping",
            "source_id": shopping["id"],
            "starts_at": "2026-08-12T17:00:00+03:00",
            "recurrence_scope": "instance",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert moved.status_code == 200
    refreshed = client.get(
        "/api/v1/calendar?start=2026-08-12T00:00:00%2B03:00&end=2026-08-13T00:00:00%2B03:00&type=shopping"
    ).json()
    assert len(refreshed) == 1


def test_notifications_are_deduplicated_readable_and_push_subscription_is_private(
    stage7_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = stage7_client
    csrf = setup(client)
    admin_id = client.get("/api/v1/auth/me").json()["user"]["id"]
    client.post(
        "/api/v1/tasks",
        json={
            "title": "Срочное дело",
            "due_at": "2026-08-01T10:30:00+00:00",
            "assignment_mode": "fixed",
            "assignee_ids": [admin_id],
        },
        headers={"X-CSRF-Token": csrf},
    )

    async def generate() -> tuple[int, int]:
        moment = datetime(2026, 8, 1, 10, tzinfo=UTC)
        async with factory.begin() as db:
            first = await generate_due_notifications(db, moment=moment)
        async with factory.begin() as db:
            second = await generate_due_notifications(db, moment=moment)
        return first, second

    first, second = asyncio.run(generate())
    assert first >= 1
    assert second == 0
    notices = client.get("/api/v1/settings/notifications?unread_only=true").json()
    assert any(item["title"] == "Срочное дело" for item in notices)
    subscribed = client.post(
        "/api/v1/settings/push/subscriptions",
        json={
            "endpoint": "https://push.example.test/subscription-123456",
            "p256dh": "public-key-material-123456789",
            "auth": "auth-secret-12345",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert subscribed.status_code == 201
    assert "endpoint" not in str(client.get("/api/v1/settings/preferences").json())
    assert (
        client.post(
            "/api/v1/settings/notifications/read-all", headers={"X-CSRF-Token": csrf}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/settings/notifications/unread-count").json()["count"] == 0
    summary = client.get("/api/v1/family/summary")
    assert summary.status_code == 200
    assert summary.json()[0]["today_tasks"] == 1
