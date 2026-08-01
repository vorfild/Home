from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.storage import StorageItem, StorageNode
from app.models.tasks import TaskDefinition, TaskInstance
from app.services.storage import process_storage_timers

TEST_PASSWORD = f"Test-{secrets.token_urlsafe(12)}-7"


@pytest.fixture
def storage_client() -> Iterator[TestClient]:
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
    return response.json()["csrf_token"]


def test_tree_search_stable_qr_and_explicit_regeneration(storage_client: TestClient) -> None:
    csrf = setup(storage_client)
    home = storage_client.post(
        "/api/v1/storage/nodes",
        json={"name": "Дом", "node_type": "помещение"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    box = storage_client.post(
        "/api/v1/storage/nodes",
        json={"name": "Коробка", "node_type": "коробка", "parent_id": home["id"]},
        headers={"X-CSRF-Token": csrf},
    ).json()
    item = storage_client.post(
        "/api/v1/storage/items",
        json={
            "name": "Набор ключей",
            "node_id": box["id"],
            "category": "инструменты",
            "tags": ["ремонт"],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert item.status_code == 201

    qr = storage_client.post(
        f"/api/v1/storage/nodes/{box['id']}/qr",
        headers={"X-CSRF-Token": csrf},
    ).json()
    storage_client.patch(
        f"/api/v1/storage/items/{item.json()['id']}",
        json={"description": "Для гаража"},
        headers={"X-CSRF-Token": csrf},
    )
    unchanged = storage_client.post(
        f"/api/v1/storage/nodes/{box['id']}/qr",
        headers={"X-CSRF-Token": csrf},
    ).json()
    assert unchanged["token"] == qr["token"]
    assert storage_client.get(f"/api/v1/storage/qr/{qr['token']}").status_code == 200

    search = storage_client.get("/api/v1/storage/search?q=ремонт")
    assert search.status_code == 200
    assert search.json()["items"][0]["path"][-1]["name"] == "Коробка"

    regenerated = storage_client.post(
        f"/api/v1/storage/nodes/{box['id']}/qr/regenerate",
        headers={"X-CSRF-Token": csrf},
    ).json()
    assert regenerated["token"] != qr["token"]
    assert storage_client.get(f"/api/v1/storage/qr/{qr['token']}").status_code == 404
    assert storage_client.get(f"/api/v1/storage/qr/{regenerated['token']}").status_code == 200


def test_used_today_never_changes_storage_timer(storage_client: TestClient) -> None:
    csrf = setup(storage_client)
    node = storage_client.post(
        "/api/v1/storage/nodes",
        json={"name": "Шкаф"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    item = storage_client.post(
        "/api/v1/storage/items",
        json={
            "name": "Куртка",
            "node_id": node["id"],
            "review_at": "2027-01-01T10:00:00+02:00",
        },
        headers={"X-CSRF-Token": csrf},
    ).json()
    used = storage_client.post(
        f"/api/v1/storage/items/{item['id']}/used-today",
        headers={"X-CSRF-Token": csrf},
    ).json()

    assert used["last_used_at"] == "2026-08-01"
    assert used["review_at"] == item["review_at"]
    assert used["review_status"] == "active"


@pytest.mark.asyncio
async def test_expired_timer_creates_exactly_one_ordinary_task() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    now = datetime.now(UTC)
    async with factory.begin() as db:
        node = StorageNode(household_id="house-1", name="Коробка", node_type="коробка")
        db.add(node)
        await db.flush()
        db.add(
            StorageItem(
                household_id="house-1",
                node_id=node.id,
                name="Палатка",
                normalized_name="палатка",
                location_since=now - timedelta(days=90),
                review_at=now - timedelta(minutes=1),
                review_status="active",
            )
        )
    async with factory.begin() as db:
        assert await process_storage_timers(db) == 1
    async with factory.begin() as db:
        assert await process_storage_timers(db) == 0
        assert await db.scalar(select(func.count(TaskDefinition.id))) == 1
        assert await db.scalar(select(func.count(TaskInstance.id))) == 1
    await engine.dispose()
