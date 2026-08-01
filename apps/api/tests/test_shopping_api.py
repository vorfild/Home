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

TEST_PASSWORD = f"Test-{secrets.token_urlsafe(12)}-7"


@pytest.fixture
def shopping_client() -> Iterator[TestClient]:
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


def setup(client: TestClient) -> tuple[str, str]:
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
    body = response.json()
    return body["csrf_token"], body["user"]["id"]


def create_list(client: TestClient, csrf: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {"title": "Продукты"}
    payload.update(extra)
    response = client.post(
        "/api/v1/shopping/lists",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.json()


def test_planned_list_appears_today_and_orders_personal_before_common(
    shopping_client: TestClient,
) -> None:
    csrf, admin_id = setup(shopping_client)
    shopping_list = create_list(
        shopping_client,
        csrf,
        scheduled_at="2026-08-01T18:00:00+03:00",
        responsible_id=admin_id,
    )
    common = shopping_client.post(
        f"/api/v1/shopping/lists/{shopping_list['id']}/items",
        json={"name": "Молоко", "recipient_id": None},
        headers={"X-CSRF-Token": csrf},
    )
    personal = shopping_client.post(
        f"/api/v1/shopping/lists/{shopping_list['id']}/items",
        json={"name": "Яблоки", "recipient_id": admin_id},
        headers={"X-CSRF-Token": csrf},
    )
    assert common.status_code == personal.status_code == 201

    today = shopping_client.get("/api/v1/shopping/today")
    assert today.status_code == 200
    assert [item["name"] for item in today.json()[0]["items"]] == ["Яблоки", "Молоко"]


def test_child_proposal_requires_adult_decision(shopping_client: TestClient) -> None:
    admin_csrf, _ = setup(shopping_client)
    shopping_list = create_list(shopping_client, admin_csrf)
    child = shopping_client.post(
        "/api/v1/family/members",
        json={"name": "Миша", "login": "misha", "role": "child"},
        headers={"X-CSRF-Token": admin_csrf},
    ).json()

    shopping_client.cookies.clear()
    child_auth = shopping_client.post(
        "/api/v1/auth/login",
        json={"login": "misha", "password": child["temporary_password"]},
    ).json()
    proposed = shopping_client.post(
        f"/api/v1/shopping/lists/{shopping_list['id']}/items",
        json={"name": "Мороженое"},
        headers={"X-CSRF-Token": child_auth["csrf_token"]},
    )
    assert proposed.status_code == 201
    assert proposed.json()["proposal_status"] == "pending"
    assert shopping_client.get("/api/v1/shopping/proposals").status_code == 403

    shopping_client.cookies.clear()
    admin = shopping_client.post(
        "/api/v1/auth/login", json={"login": "alexey", "password": TEST_PASSWORD}
    ).json()
    proposals = shopping_client.get("/api/v1/shopping/proposals")
    assert [item["name"] for item in proposals.json()] == ["Мороженое"]
    accepted = shopping_client.post(
        f"/api/v1/shopping/proposals/{proposed.json()['id']}/decision",
        json={"decision": "accept"},
        headers={"X-CSRF-Token": admin["csrf_token"]},
    )
    assert accepted.status_code == 200
    assert accepted.json()["proposal_status"] == "accepted"


def test_duplicate_warning_and_offline_operation_are_idempotent(
    shopping_client: TestClient,
) -> None:
    csrf, _ = setup(shopping_client)
    first = create_list(shopping_client, csrf)
    second = create_list(shopping_client, csrf, title="Хозяйственное")
    operation_id = "offline-operation-0001"
    created = shopping_client.post(
        f"/api/v1/shopping/lists/{first['id']}/items",
        json={"name": "Бумага", "client_operation_id": operation_id},
        headers={"X-CSRF-Token": csrf},
    )
    repeated = shopping_client.post(
        f"/api/v1/shopping/lists/{first['id']}/items",
        json={"name": "Бумага", "client_operation_id": operation_id},
        headers={"X-CSRF-Token": csrf},
    )
    duplicate = shopping_client.post(
        f"/api/v1/shopping/lists/{second['id']}/items",
        json={"name": "бумага"},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.json()["id"] == repeated.json()["id"]
    assert duplicate.json()["duplicate_warning"] is True
