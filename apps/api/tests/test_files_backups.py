from __future__ import annotations

import asyncio
import io
import secrets
import zipfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db_session
from app.main import app
from app.models.files import BackupArchive, FileAsset
from app.models.identity import Household
from app.services.backups import ArchiveError, create_archive, create_monthly_if_due, verify_archive

TEST_PASSWORD = f"Test-{secrets.token_urlsafe(12)}-7"


@pytest.fixture
def data_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, async_sessionmaker[AsyncSession]]]:
    settings = get_settings()
    monkeypatch.setattr(settings, "files_dir", tmp_path / "files")
    monkeypatch.setattr(settings, "backups_dir", tmp_path / "backups")
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


def storage_item(client: TestClient, csrf: str) -> tuple[dict[str, object], dict[str, object]]:
    node = client.post(
        "/api/v1/storage/nodes",
        json={"name": "Кладовая"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    item = client.post(
        "/api/v1/storage/items",
        json={"node_id": node["id"], "name": "Фотоальбом"},
        headers={"X-CSRF-Token": csrf},
    ).json()
    return node, item


def png_bytes(width: int = 2400, height: int = 1200) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (width, height), (80, 130, 170)).save(stream, "PNG")
    return stream.getvalue()


def upload(client: TestClient, csrf: str, item_id: str, content: bytes) -> dict[str, object]:
    response = client.post(
        f"/api/v1/files?entity_type=storage_item&entity_id={item_id}&purpose=photo",
        content=content,
        headers={
            "X-CSRF-Token": csrf,
            "Content-Type": "image/png",
            "X-Filename": "family-photo.png",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_image_upload_is_resized_private_and_has_thumbnail(
    data_client: tuple[TestClient, object],
) -> None:
    client = data_client[0]
    csrf = setup(client)
    _, item = storage_item(client, csrf)
    asset = upload(client, csrf, str(item["id"]), png_bytes())
    assert asset["stored_mime"] == "image/webp"
    assert asset["width"] == 2048
    assert asset["height"] == 1024
    assert asset["is_primary"] is True
    thumbnail = client.get(f"/api/v1/files/{asset['id']}?thumbnail=true")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    assert thumbnail.headers["cache-control"] == "no-store"

    invalid = client.post(
        f"/api/v1/files?entity_type=storage_item&entity_id={item['id']}",
        content=b"not-an-image",
        headers={
            "X-CSRF-Token": csrf,
            "Content-Type": "image/png",
            "X-Filename": "fake.png",
        },
    )
    assert invalid.status_code == 415
    client.cookies.clear()
    assert client.get(f"/api/v1/files/{asset['id']}").status_code == 401


def test_monthly_copy_is_single_atomic_and_old_copy_survives_failure(
    data_client: tuple[TestClient, async_sessionmaker[AsyncSession]],
) -> None:
    client, factory = data_client
    csrf = setup(client)
    _, item = storage_item(client, csrf)
    upload(client, csrf, str(item["id"]), png_bytes(320, 200))

    async def monthly() -> tuple[bool, bool, str, str]:
        async with factory.begin() as db:
            first = await create_monthly_if_due(db)
        async with factory.begin() as db:
            second = await create_monthly_if_due(db)
        async with factory() as db:
            record = await db.scalar(select(BackupArchive).where(BackupArchive.kind == "monthly"))
            asset = await db.scalar(select(FileAsset))
            assert record is not None and asset is not None
            return first, second, record.path, asset.stored_path

    first, second, relative, stored = asyncio.run(monthly())
    assert first is True and second is False
    target = get_settings().backups_dir / relative
    before = target.read_bytes()
    (get_settings().files_dir / stored).unlink()

    async def failed_replacement() -> None:
        async with factory() as db:
            household_id = await db.scalar(select(Household.id))
            assert household_id
            with pytest.raises(ArchiveError):
                await create_archive(
                    db,
                    household_id=household_id,
                    created_by_id=None,
                    kind="monthly",
                )

    asyncio.run(failed_replacement())
    assert target.read_bytes() == before
    assert len(list((get_settings().backups_dir / "monthly").glob("*.zip"))) == 1


def test_export_import_restores_qr_files_and_revokes_sessions(
    data_client: tuple[TestClient, object],
) -> None:
    client = data_client[0]
    csrf = setup(client)
    node, item = storage_item(client, csrf)
    asset = upload(client, csrf, str(item["id"]), png_bytes(400, 240))
    qr = client.post(
        f"/api/v1/storage/nodes/{node['id']}/qr", headers={"X-CSRF-Token": csrf}
    ).json()
    created = client.post("/api/v1/data/exports", headers={"X-CSRF-Token": csrf})
    assert created.status_code == 201, created.text
    backup = created.json()
    archive = client.get(f"/api/v1/data/backups/{backup['id']}/download").content
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert {"manifest.json", "database.json"}.issubset(zipped.namelist())
        assert any(name.startswith("files/objects/") for name in zipped.namelist())

    changed = client.patch(
        f"/api/v1/storage/nodes/{node['id']}",
        json={"name": "Изменено"},
        headers={"X-CSRF-Token": csrf},
    )
    assert changed.status_code == 200
    regenerated = client.post(
        f"/api/v1/storage/nodes/{node['id']}/qr/regenerate",
        headers={"X-CSRF-Token": csrf},
    ).json()
    assert regenerated["token"] != qr["token"]

    restored = client.post(
        "/api/v1/data/imports",
        content=archive,
        headers={
            "X-CSRF-Token": csrf,
            "Content-Type": "application/zip",
            "X-Filename": "domovoy-export.zip",
            "X-Domovoy-Admin-Password": TEST_PASSWORD,
        },
    )
    assert restored.status_code == 201, restored.text
    assert restored.json()["status"] == "completed"
    assert client.get("/api/v1/auth/me").status_code == 401

    client.cookies.clear()
    logged_in = client.post(
        "/api/v1/auth/login", json={"login": "alexey", "password": TEST_PASSWORD}
    )
    assert logged_in.status_code == 200
    tree = client.get("/api/v1/storage/tree").json()
    assert tree[0]["name"] == "Кладовая"
    assert client.get(f"/api/v1/storage/qr/{qr['token']}").status_code == 200
    assert client.get(f"/api/v1/files/{asset['id']}?thumbnail=true").status_code == 200


def test_archive_tampering_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "tampered.zip"
    database = b'{"format":1,"tables":{}}'
    manifest = {
        "format": 1,
        "checksums": {"database.json": "0" * 64},
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("database.json", database)
        archive.writestr("manifest.json", __import__("json").dumps(manifest))
    with pytest.raises(ArchiveError):
        verify_archive(path)
