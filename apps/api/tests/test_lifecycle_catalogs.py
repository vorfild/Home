from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.lifecycle import Category, TrashEntry
from app.models.storage import StorageNode
from app.services.auth import now_utc
from app.services.lifecycle import purge_expired_trash

PASSWORD = "Release-Test-Password-2026"


@pytest.fixture
def lifecycle_client() -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
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
            "admin_password": PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.json()["csrf_token"]


def test_catalog_defaults_and_server_side_permissions(
    lifecycle_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = lifecycle_client
    csrf = setup(client)
    assert len(client.get("/api/v1/catalogs/categories/task").json()) == 6
    assert len(client.get("/api/v1/catalogs/categories/shopping").json()) == 5
    assert len(client.get("/api/v1/catalogs/categories/storage").json()) == 7
    custom_category = client.post(
        "/api/v1/catalogs/categories/storage",
        json={
            "name": "Спорт",
            "sort_order": 20,
            "color": "#336699",
            "icon": "dumbbell",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert custom_category.status_code == 201
    edited_category = client.patch(
        f"/api/v1/catalogs/categories/storage/{custom_category.json()['id']}",
        json={"name": "Спорт и отдых", "sort_order": 8, "color": "#123456", "icon": "tent"},
        headers={"X-CSRF-Token": csrf},
    )
    assert edited_category.status_code == 200
    assert edited_category.json()["name"] == "Спорт и отдых"
    assert edited_category.json()["sort_order"] == 8
    room = client.post(
        "/api/v1/catalogs/rooms",
        json={"name": "Кухня", "color": "#8DB8A8", "icon": "home"},
        headers={"X-CSRF-Token": csrf},
    )
    assert room.status_code == 201
    disabled = client.patch(
        f"/api/v1/catalogs/rooms/{room.json()['id']}",
        json={"is_active": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert disabled.status_code == 200
    assert client.get("/api/v1/catalogs/rooms").json() == []
    assert len(client.get("/api/v1/catalogs/rooms?include_inactive=true").json()) == 1

    child = client.post(
        "/api/v1/family/members",
        json={"name": "Миша", "login": "misha", "role": "child"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    client.cookies.clear()
    child_auth = client.post(
        "/api/v1/auth/login",
        json={"login": "misha", "password": child["temporary_password"]},
    ).json()
    assert client.get("/api/v1/catalogs/categories/task").status_code == 200
    forbidden = client.post(
        "/api/v1/catalogs/rooms",
        json={"name": "Детская"},
        headers={"X-CSRF-Token": child_auth["csrf_token"]},
    )
    assert forbidden.status_code == 403
    assert client.get("/api/v1/lifecycle/archive").status_code == 403

    async def category_count() -> int:
        async with factory() as db:
            return int(await db.scalar(select(func.count(Category.id))) or 0)

    assert asyncio.run(category_count()) == 19


def test_archive_trash_restore_and_stable_storage_qr(
    lifecycle_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = lifecycle_client
    csrf = setup(client)
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Разовая уборка", "assignment_mode": "anyone", "repeat": {"kind": "none"}},
        headers={"X-CSRF-Token": csrf},
    ).json()
    completed = client.post(
        f"/api/v1/tasks/{task['id']}/complete",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert completed.status_code == 200
    assert any(
        item["title"] == "Разовая уборка" for item in client.get("/api/v1/lifecycle/archive").json()
    )

    trashed_task = client.delete(
        f"/api/v1/tasks/{task['definition_id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert trashed_task.status_code == 200
    assert client.get("/api/v1/tasks?view=completed").json() == []
    task_trash = next(
        item
        for item in client.get("/api/v1/lifecycle/trash").json()
        if item["entity_type"] == "task"
    )
    restored_task = client.post(
        f"/api/v1/lifecycle/trash/{task_trash['id']}/restore",
        headers={"X-CSRF-Token": csrf},
    )
    assert restored_task.status_code == 200
    assert len(client.get("/api/v1/tasks?view=completed").json()) == 1

    node = client.post(
        "/api/v1/storage/nodes",
        json={"name": "Архивная коробка"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    client.post(
        "/api/v1/storage/items",
        json={"name": "Письма", "node_id": node["id"]},
        headers={"X-CSRF-Token": csrf},
    )
    qr = client.post(
        f"/api/v1/storage/nodes/{node['id']}/qr",
        headers={"X-CSRF-Token": csrf},
    ).json()
    deleted = client.post(
        f"/api/v1/storage/nodes/{node['id']}/delete",
        json={"strategy": "delete", "file_action": "keep"},
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/storage/qr/{qr['token']}").status_code == 404
    entry = next(
        item
        for item in client.get("/api/v1/lifecycle/trash").json()
        if item["entity_type"] == "storage_node"
    )
    assert (
        client.post(
            f"/api/v1/lifecycle/trash/{entry['id']}/restore",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 200
    )
    assert client.get(f"/api/v1/storage/qr/{qr['token']}").status_code == 200

    deleted_again = client.post(
        f"/api/v1/storage/nodes/{node['id']}/delete",
        json={"strategy": "delete", "file_action": "delete"},
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted_again.status_code == 200

    async def expire_and_purge() -> tuple[int, int]:
        async with factory.begin() as db:
            entry_record = await db.scalar(
                select(TrashEntry).where(TrashEntry.entity_type == "storage_node")
            )
            assert entry_record is not None
            entry_record.purge_after = now_utc()
        async with factory.begin() as db:
            purged = await purge_expired_trash(db)
        async with factory() as db:
            remaining = int(await db.scalar(select(func.count(StorageNode.id))) or 0)
        return purged.count, remaining

    assert asyncio.run(expire_and_purge()) == (1, 0)
