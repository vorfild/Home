from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db_session
from app.main import app


@pytest.fixture
def identity_client() -> Iterator[TestClient]:
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


def setup_admin(client: TestClient) -> tuple[dict[str, object], str]:
    response = client.post(
        "/api/v1/setup",
        json={
            "language": "ru",
            "timezone": "Europe/Moscow",
            "household_name": "Дом тестов",
            "admin_name": "Алексей",
            "admin_login": "alexey",
            "admin_password": "Secure-Password-2026",
            "notifications": {"in_app": True, "web_push": False, "email": False},
        },
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    return body, body["csrf_token"]


def test_first_setup_is_atomic_and_creates_authenticated_admin(
    identity_client: TestClient,
) -> None:
    assert identity_client.get("/api/v1/setup/status").json() == {"setup_required": True}

    body, _ = setup_admin(identity_client)

    assert body["user"]["role"] == "admin"
    assert body["user"]["must_change_password"] is False
    assert identity_client.get("/api/v1/setup/status").json() == {"setup_required": False}
    assert identity_client.get("/api/v1/auth/me").status_code == 200
    duplicate = identity_client.post(
        "/api/v1/setup",
        json={
            "language": "ru",
            "timezone": "Europe/Moscow",
            "household_name": "Другой дом",
            "admin_name": "Другой",
            "admin_login": "another",
            "admin_password": "Another-Password-2026",
        },
    )
    assert duplicate.status_code == 409


def test_admin_creates_adult_and_server_enforces_role_and_csrf(
    identity_client: TestClient,
) -> None:
    _, csrf = setup_admin(identity_client)
    payload = {"name": "Анна", "login": "anna", "role": "adult", "color": "#8DB8A8"}

    assert identity_client.post("/api/v1/family/members", json=payload).status_code == 403
    created = identity_client.post(
        "/api/v1/family/members", json=payload, headers={"X-CSRF-Token": csrf}
    )

    assert created.status_code == 201
    temporary_password = created.json()["temporary_password"]
    adult_id = created.json()["user"]["id"]
    assert created.json()["user"]["must_change_password"] is True

    identity_client.cookies.clear()
    login = identity_client.post(
        "/api/v1/auth/login", json={"login": "ANNA", "password": temporary_password}
    )
    assert login.status_code == 200
    adult_csrf = login.json()["csrf_token"]
    forbidden = identity_client.post(
        "/api/v1/family/members",
        json={"name": "Миша", "login": "misha", "role": "child"},
        headers={"X-CSRF-Token": adult_csrf},
    )
    assert forbidden.status_code == 403

    changed = identity_client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": temporary_password,
            "new_password": "Permanent-Password-42",
        },
        headers={"X-CSRF-Token": adult_csrf},
    )
    assert changed.status_code == 200
    assert changed.json()["user"]["must_change_password"] is False
    assert changed.json()["user"]["id"] == adult_id


def test_shared_tablet_uses_trusted_device_and_pin(identity_client: TestClient) -> None:
    _, csrf = setup_admin(identity_client)
    child = identity_client.post(
        "/api/v1/family/members",
        json={"name": "Миша", "login": "misha", "role": "child", "color": "#5E7FA3"},
        headers={"X-CSRF-Token": csrf},
    ).json()["user"]
    pin_response = identity_client.put(
        f"/api/v1/family/members/{child['id']}/pin",
        json={"pin": "2468"},
        headers={"X-CSRF-Token": csrf},
    )
    assert pin_response.status_code == 200
    registered = identity_client.post(
        "/api/v1/family/tablets",
        json={"name": "Планшет на кухне"},
        headers={"X-CSRF-Token": csrf},
    )
    assert registered.status_code == 201

    users = identity_client.get("/api/v1/tablet/users")
    assert [user["name"] for user in users.json()] == ["Миша"]
    wrong_pin = identity_client.post(
        "/api/v1/tablet/login", json={"user_id": child["id"], "pin": "1111"}
    )
    assert wrong_pin.status_code == 401
    signed_in = identity_client.post(
        "/api/v1/tablet/login", json={"user_id": child["id"], "pin": "2468"}
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["user"]["role"] == "child"


def test_disabling_user_revokes_existing_session(identity_client: TestClient) -> None:
    _, admin_csrf = setup_admin(identity_client)
    created = identity_client.post(
        "/api/v1/family/members",
        json={"name": "Анна", "login": "anna", "role": "adult"},
        headers={"X-CSRF-Token": admin_csrf},
    ).json()
    identity_client.cookies.clear()
    adult_login = identity_client.post(
        "/api/v1/auth/login",
        json={"login": "anna", "password": created["temporary_password"]},
    )
    assert adult_login.status_code == 200
    adult_cookies = dict(identity_client.cookies)

    identity_client.cookies.clear()
    admin_login = identity_client.post(
        "/api/v1/auth/login",
        json={"login": "alexey", "password": "Secure-Password-2026"},
    ).json()
    disabled = identity_client.patch(
        f"/api/v1/family/members/{created['user']['id']}",
        json={"is_active": False},
        headers={"X-CSRF-Token": admin_login["csrf_token"]},
    )
    assert disabled.status_code == 200

    identity_client.cookies.clear()
    identity_client.cookies.update(adult_cookies)
    assert identity_client.get("/api/v1/auth/me").status_code == 401
    assert (
        identity_client.post(
            "/api/v1/auth/login",
            json={"login": "anna", "password": created["temporary_password"]},
        ).status_code
        == 401
    )


def test_absence_dates_and_overlap_are_validated(identity_client: TestClient) -> None:
    _, csrf = setup_admin(identity_client)
    child = identity_client.post(
        "/api/v1/family/members",
        json={"name": "Миша", "login": "misha", "role": "child"},
        headers={"X-CSRF-Token": csrf},
    ).json()["user"]
    payload = {"starts_on": "2026-08-10", "ends_on": "2026-08-20", "note": "Лагерь"}

    created = identity_client.post(
        f"/api/v1/family/members/{child['id']}/absences",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )

    assert created.status_code == 201
    listed = identity_client.get(f"/api/v1/family/members/{child['id']}/absences")
    assert listed.status_code == 200
    assert listed.json()[0]["note"] == "Лагерь"
    overlap = identity_client.post(
        f"/api/v1/family/members/{child['id']}/absences",
        json={"starts_on": "2026-08-19", "ends_on": "2026-08-22"},
        headers={"X-CSRF-Token": csrf},
    )
    assert overlap.status_code == 409
