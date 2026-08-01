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
def sync_client() -> Iterator[TestClient]:
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


def create_task(client: TestClient, csrf: str, *, recurring: bool = False) -> dict[str, object]:
    response = client.post(
        "/api/v1/tasks",
        json={
            "title": "Полить цветы",
            "description": "Утром",
            "due_at": "2026-08-02T10:00:00+03:00",
            "assignment_mode": "anyone",
            "repeat": {"kind": "weekly" if recurring else "none"},
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 201
    return response.json()


def change(
    client: TestClient,
    csrf: str,
    task: dict[str, object],
    *,
    operation: str,
    base: int,
    values: dict[str, object],
):
    return client.post(
        "/api/v1/sync/changes",
        json={
            "client_operation_id": operation,
            "entity_type": "task",
            "entity_id": task["definition_id"],
            "base_version": base,
            "changes": values,
        },
        headers={"X-CSRF-Token": csrf},
    )


def test_different_fields_merge_and_same_field_conflict_is_preserved(
    sync_client: TestClient,
) -> None:
    csrf = setup(sync_client)
    task = create_task(sync_client, csrf)
    version = sync_client.get(f"/api/v1/sync/version/task/{task['definition_id']}").json()
    assert version["version"] == 1

    first = change(
        sync_client,
        csrf,
        task,
        operation="desktop-operation-1",
        base=1,
        values={"title": "Полить растения"},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "applied"

    merged = change(
        sync_client,
        csrf,
        task,
        operation="offline-operation-2",
        base=1,
        values={"description": "После завтрака"},
    )
    assert merged.status_code == 200
    assert merged.json()["status"] == "merged"
    assert merged.json()["state"]["title"] == "Полить растения"
    assert merged.json()["state"]["description"] == "После завтрака"

    conflicted = change(
        sync_client,
        csrf,
        task,
        operation="offline-operation-3",
        base=1,
        values={"title": "Полить пальму"},
    )
    assert conflicted.status_code == 200
    assert conflicted.json()["status"] == "conflict"
    assert conflicted.json()["state"]["title"] == "Полить растения"
    conflict = sync_client.get("/api/v1/sync/conflicts").json()[0]
    assert conflict["server_value"] == "Полить растения"
    assert conflict["alternative_value"] == "Полить пальму"

    resolved = sync_client.post(
        f"/api/v1/sync/conflicts/{conflict['id']}/resolve",
        json={"resolution": "alternative"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resolved.status_code == 200
    final = sync_client.get(f"/api/v1/sync/version/task/{task['definition_id']}").json()
    assert final["state"]["title"] == "Полить пальму"
    assert final["has_conflict"] is False


def test_five_conflicts_create_one_admin_notice_and_reject_all(sync_client: TestClient) -> None:
    csrf = setup(sync_client)
    tasks = [create_task(sync_client, csrf) for _ in range(5)]
    for index, task in enumerate(tasks):
        sync_client.get(f"/api/v1/sync/version/task/{task['definition_id']}")
        assert (
            change(
                sync_client,
                csrf,
                task,
                operation=f"server-operation-{index}",
                base=1,
                values={"title": f"Сервер {index}"},
            ).status_code
            == 200
        )
        assert (
            change(
                sync_client,
                csrf,
                task,
                operation=f"offline-operation-{index}",
                base=1,
                values={"title": f"Офлайн {index}"},
            ).json()["status"]
            == "conflict"
        )

    notices = sync_client.get("/api/v1/settings/notifications").json()
    assert len([item for item in notices if item["event_type"] == "sync_conflicts"]) == 1
    rejected = sync_client.post("/api/v1/sync/conflicts/reject-all", headers={"X-CSRF-Token": csrf})
    assert rejected.status_code == 200
    assert sync_client.get("/api/v1/sync/conflicts").json() == []


def test_offline_completion_is_idempotent_and_mutations_emit_events(
    sync_client: TestClient,
) -> None:
    csrf = setup(sync_client)
    task = create_task(sync_client, csrf, recurring=True)
    payload = {
        "client_operation_id": "offline-complete-123",
        "completed_subtask_ids": [],
    }
    first = sync_client.post(
        f"/api/v1/tasks/{task['id']}/complete",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    second = sync_client.post(
        f"/api/v1/tasks/{task['id']}/complete",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == second.status_code == 200
    recurring = sync_client.get("/api/v1/tasks?view=recurring").json()
    assert len(recurring) == 1
    assert recurring[0]["status"] == "open"
    events = sync_client.get("/api/v1/sync/events").json()
    assert any(item["entity_type"] == "tasks" for item in events)


def test_child_cannot_submit_generic_sync_change(sync_client: TestClient) -> None:
    csrf = setup(sync_client)
    task = create_task(sync_client, csrf)
    child = sync_client.post(
        "/api/v1/family/members",
        json={"name": "Миша", "login": "misha", "role": "child"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    sync_client.cookies.clear()
    auth = sync_client.post(
        "/api/v1/auth/login",
        json={"login": "misha", "password": child["temporary_password"]},
    ).json()
    forbidden = change(
        sync_client,
        auth["csrf_token"],
        task,
        operation="child-operation-1",
        base=1,
        values={"title": "Удалить всё"},
    )
    assert forbidden.status_code == 403
