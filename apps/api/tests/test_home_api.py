from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.home import MaintenanceRecord
from app.services.home import process_maintenance_schedules, purge_expired_repair_history

TEST_PASSWORD = f"Test-{secrets.token_urlsafe(12)}-7"


@pytest.fixture
def home_client() -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
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


def test_linked_equipment_uses_storage_identity(home_client: tuple[TestClient, object]) -> None:
    client = home_client[0]
    csrf = setup(client)
    node = client.post(
        "/api/v1/storage/nodes",
        json={"name": "Котельная"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    stored = client.post(
        "/api/v1/storage/items",
        json={
            "name": "Газовый котёл",
            "node_id": node["id"],
            "category": "отопление",
            "manufacturer": "Тепло",
        },
        headers={"X-CSRF-Token": csrf},
    ).json()
    linked = client.post(
        "/api/v1/home/equipment",
        json={"storage_item_id": stored["id"], "name": "Дубликат", "location": "Другое"},
        headers={"X-CSRF-Token": csrf},
    )

    assert linked.status_code == 201
    assert linked.json()["name"] == "Газовый котёл"
    assert linked.json()["location"] == "Котельная"
    assert linked.json()["manufacturer"] == "Тепло"


def test_due_maintenance_creates_one_task_and_completion_history(
    home_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = home_client
    csrf = setup(client)
    plan = client.post(
        "/api/v1/home/maintenance",
        json={
            "title": "Промыть фильтр",
            "interval_days": 30,
            "next_on": "2026-07-01",
            "checklist": ["Перекрыть воду", "Промыть"],
        },
        headers={"X-CSRF-Token": csrf},
    ).json()

    async def run_schedule() -> tuple[int, int]:
        async with factory.begin() as db:
            first = await process_maintenance_schedules(db, today=date(2026, 8, 1))
        async with factory.begin() as db:
            second = await process_maintenance_schedules(db, today=date(2026, 8, 1))
        return first, second

    assert asyncio.run(run_schedule()) == (1, 0)
    tasks = client.get("/api/v1/tasks").json()
    task = next(item for item in tasks if item["source_type"] == "maintenance")
    completed = client.post(
        f"/api/v1/tasks/{task['id']}/complete",
        json={
            "completed_subtask_ids": [item["id"] for item in task["subtasks"]],
            "comment": "Без протечек",
            "actual_cost": 350,
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert completed.status_code == 200
    history = client.get("/api/v1/home/repairs?record_type=maintenance").json()
    assert len(history) == 1
    assert history[0]["plan_id"] == plan["id"]
    assert history[0]["comment"] == "Без протечек"
    refreshed = client.get("/api/v1/home/maintenance").json()[0]
    assert refreshed["open_task_id"] is None
    assert refreshed["previous_on"] == "2026-08-01"
    assert refreshed["next_on"] == "2026-08-31"


def test_meter_consumption_warning_reset_and_module_retention(
    home_client: tuple[TestClient, object],
) -> None:
    client = home_client[0]
    csrf = setup(client)
    meter = client.post(
        "/api/v1/home/meters",
        json={"meter_type": "Электричество", "unit": "кВт·ч", "location": "Прихожая"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    for value in (100, 125):
        response = client.post(
            f"/api/v1/home/meters/{meter['id']}/readings",
            json={"value": value, "read_on": "2026-08-01"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 201
    assert response.json()["consumption"] == "25.0000"
    refused = client.post(
        f"/api/v1/home/meters/{meter['id']}/readings",
        json={"value": 12, "read_on": "2026-08-02"},
        headers={"X-CSRF-Token": csrf},
    )
    assert refused.status_code == 409
    replacement = client.post(
        f"/api/v1/home/meters/{meter['id']}/replace",
        json={"serial_number": "NEW-1", "start_value": 5, "replaced_on": "2026-08-02"},
        headers={"X-CSRF-Token": csrf},
    )
    assert replacement.status_code == 200
    assert replacement.json()["reset_sequence"] == 1

    disabled = client.put(
        "/api/v1/home/meters/module",
        json={"enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert disabled.json() == {"enabled": False}
    assert client.get("/api/v1/home/meters").status_code == 409
    client.put(
        "/api/v1/home/meters/module",
        json={"enabled": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert len(client.get(f"/api/v1/home/meters/{meter['id']}/readings").json()) == 3


@pytest.mark.asyncio
async def test_repair_retention_deletes_only_expired_non_permanent_records() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    expired = datetime.now(UTC) - timedelta(minutes=1)
    async with factory.begin() as db:
        db.add_all(
            [
                MaintenanceRecord(
                    household_id="house-1",
                    title="Старый ремонт",
                    performed_on=date(2024, 1, 1),
                    purge_after=expired,
                    keep_forever=False,
                ),
                MaintenanceRecord(
                    household_id="house-1",
                    title="Важный ремонт",
                    performed_on=date(2024, 1, 1),
                    purge_after=expired,
                    keep_forever=True,
                ),
            ]
        )
    async with factory.begin() as db:
        assert await purge_expired_repair_history(db) == 1
    async with factory.begin() as db:
        assert await db.scalar(select(func.count(MaintenanceRecord.id))) == 1
    await engine.dispose()
