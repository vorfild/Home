from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.services.tasks import next_due_at

TEST_ADMIN_PASSWORD = f"Test-{secrets.token_urlsafe(12)}-7"


@pytest.fixture
def task_client() -> Iterator[TestClient]:
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
            yield client
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


def setup(task_client: TestClient) -> str:
    response = task_client.post(
        "/api/v1/setup",
        json={
            "timezone": "Europe/Moscow",
            "household_name": "Дом",
            "admin_name": "Алексей",
            "admin_login": "alexey",
            "admin_password": TEST_ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()["csrf_token"]


def create_member(
    client: TestClient, csrf: str, *, name: str, login: str, role: str
) -> dict[str, object]:
    response = client.post(
        "/api/v1/family/members",
        json={"name": name, "login": login, "role": role},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.json()


def test_queue_skips_absent_member_and_uses_substitute(task_client: TestClient) -> None:
    csrf = setup(task_client)
    child = create_member(task_client, csrf, name="Миша", login="misha", role="child")
    adult = create_member(task_client, csrf, name="Анна", login="anna", role="adult")
    absence = task_client.post(
        f"/api/v1/family/members/{child['user']['id']}/absences",  # type: ignore[index]
        json={
            "starts_on": "2026-08-01",
            "ends_on": "2026-08-31",
            "substitute_user_id": adult["user"]["id"],  # type: ignore[index]
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert absence.status_code == 201

    created = task_client.post(
        "/api/v1/tasks",
        json={
            "title": "Вынести мусор",
            "due_at": "2026-08-10T18:00:00+03:00",
            "assignment_mode": "queue",
            "queue_user_ids": [child["user"]["id"], adult["user"]["id"]],  # type: ignore[index]
            "repeat": {"kind": "weekly"},
        },
        headers={"X-CSRF-Token": csrf},
    )

    assert created.status_code == 201
    assert created.json()["current_queue_user_id"] == adult["user"]["id"]  # type: ignore[index]
    assert created.json()["next_queue_user_id"] == adult["user"]["id"]  # type: ignore[index]


def test_child_review_creates_one_next_recurring_instance(task_client: TestClient) -> None:
    admin_csrf = setup(task_client)
    child = create_member(task_client, admin_csrf, name="Миша", login="misha", role="child")
    child_id = child["user"]["id"]  # type: ignore[index]
    created = task_client.post(
        "/api/v1/tasks",
        json={
            "title": "Полить цветы",
            "due_at": "2026-08-01T18:00:00+03:00",
            "assignment_mode": "fixed",
            "assignee_ids": [child_id],
            "subtasks": ["Проверить землю"],
            "repeat": {"kind": "weekly"},
            "requires_adult_review": True,
        },
        headers={"X-CSRF-Token": admin_csrf},
    )
    assert created.status_code == 201
    task = created.json()

    task_client.cookies.clear()
    child_login = task_client.post(
        "/api/v1/auth/login",
        json={"login": "misha", "password": child["temporary_password"]},
    ).json()
    submitted = task_client.post(
        f"/api/v1/tasks/{task['id']}/complete",
        json={"completed_subtask_ids": [task["subtasks"][0]["id"]]},
        headers={"X-CSRF-Token": child_login["csrf_token"]},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "awaiting_review"

    task_client.cookies.clear()
    admin = task_client.post(
        "/api/v1/auth/login",
        json={"login": "alexey", "password": TEST_ADMIN_PASSWORD},
    ).json()
    reviewed = task_client.post(
        f"/api/v1/tasks/{task['id']}/review",
        json={"decision": "approve"},
        headers={"X-CSRF-Token": admin["csrf_token"]},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "completed"
    recurring = task_client.get("/api/v1/tasks?view=recurring")
    assert recurring.status_code == 200
    assert len(recurring.json()) == 1
    assert recurring.json()[0]["status"] == "open"


def test_repeat_rules_handle_month_end_and_after_completion() -> None:
    from datetime import UTC, datetime

    previous = datetime(2026, 1, 31, 18, tzinfo=UTC)
    completed = datetime(2026, 2, 2, 12, tzinfo=UTC)

    assert next_due_at(previous, completed, {"kind": "monthly"}) == datetime(
        2026, 2, 28, 18, tzinfo=UTC
    )
    assert next_due_at(
        previous,
        completed,
        {"kind": "after_completion", "unit": "days", "interval": 3},
    ) == datetime(2026, 2, 5, 12, tzinfo=UTC)
