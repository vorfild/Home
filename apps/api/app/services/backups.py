from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Numeric,
    Time,
    delete,
    func,
    insert,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.base import Base
from app.models.files import BackupArchive, FileAsset
from app.models.identity import Session, new_id
from app.services.auth import now_utc
from app.services.files import sha256_file

APP_VERSION = "0.9.0"
CURRENT_SCHEMA = "0009_files_backups_transfer"
SCHEMA_ORDER = [
    "0001_project_foundation",
    "0002_identity_and_family",
    "0003_tasks_and_today",
    "0004_shopping",
    "0005_storage",
    "0006_home",
    "0007_calendar_notifications_settings",
    "0008_realtime_offline_conflicts",
    CURRENT_SCHEMA,
]
CONTROL_TABLES = {"backup_archives", "restore_reports"}
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
BackupKind = Literal["monthly", "manual", "insurance"]


class ArchiveError(ValueError):
    pass


def encoded(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    return value


def decoded(column: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict) and "$bytes" in value:
        return bytes.fromhex(str(value["$bytes"]))
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(str(value))
    if isinstance(column.type, Date):
        return date.fromisoformat(str(value))
    if isinstance(column.type, Time):
        return time.fromisoformat(str(value))
    if isinstance(column.type, Numeric):
        return Decimal(str(value))
    if isinstance(column.type, Boolean):
        return bool(value)
    return value


async def schema_version(db: AsyncSession) -> str:
    connection = await db.connection()
    exists = await connection.run_sync(
        lambda sync_connection: inspect(sync_connection).has_table("alembic_version")
    )
    if not exists:
        return CURRENT_SCHEMA
    value = await db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    return str(value or CURRENT_SCHEMA)


def backup_tables() -> list[Any]:
    return [table for table in Base.metadata.sorted_tables if table.name not in CONTROL_TABLES]


async def database_snapshot(db: AsyncSession) -> dict[str, Any]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in backup_tables():
        rows = (await db.execute(select(table))).mappings().all()
        tables[table.name] = [{key: encoded(value) for key, value in row.items()} for row in rows]
    return {"format": 1, "tables": tables}


def json_payload(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def postgres_connection() -> tuple[list[str], dict[str, str]] | None:
    value = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(value)
    database_name = parsed.path.lstrip("/")
    if parsed.scheme != "postgresql" or not parsed.hostname or not database_name:
        return None
    arguments = [
        "--host",
        parsed.hostname,
        "--port",
        str(parsed.port or 5432),
        "--username",
        unquote(parsed.username or ""),
        "--dbname",
        database_name,
    ]
    environment = dict(os.environ)
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    return arguments, environment


def create_postgres_dump(target: Path) -> bool:
    connection = postgres_connection()
    if connection is None:
        return False
    arguments, environment = connection
    subprocess.run(
        [
            "pg_dump",
            *arguments,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(target),
        ],
        check=True,
        env=environment,
        capture_output=True,
    )
    return True


def restore_postgres_dump(source: Path) -> bool:
    connection = postgres_connection()
    if connection is None:
        return False
    arguments, environment = connection
    subprocess.run(
        [
            "pg_restore",
            *arguments,
            "--clean",
            "--if-exists",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            str(source),
        ],
        check=True,
        env=environment,
        capture_output=True,
    )
    return True


def extract_postgres_dump(archive_path: Path, target: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        with archive.open("database.pgcustom") as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name


def verify_archive(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0 or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("Некорректный размер архива")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if (
                len(infos) > 100_000
                or sum(item.file_size for item in infos) > MAX_ARCHIVE_BYTES
                or any(not safe_member(item.filename) for item in infos)
            ):
                raise ArchiveError("Архив содержит недопустимые пути")
            if (
                "manifest.json" not in archive.namelist()
                or "database.json" not in archive.namelist()
            ):
                raise ArchiveError("В архиве нет манифеста или базы")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != 1 or not isinstance(manifest.get("checksums"), dict):
                raise ArchiveError("Версия формата архива не поддерживается")
            for name, expected in manifest["checksums"].items():
                if name not in archive.namelist() or not safe_member(name):
                    raise ArchiveError(f"В архиве отсутствует {name}")
                actual = hashlib.sha256(archive.read(name)).hexdigest()
                if actual != expected:
                    raise ArchiveError(f"Нарушена контрольная сумма {name}")
            database = json.loads(archive.read("database.json"))
            if database.get("format") != 1 or not isinstance(database.get("tables"), dict):
                raise ArchiveError("Некорректный снимок базы")
            return manifest
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        raise ArchiveError("Архив повреждён") from exc


async def build_archive(db: AsyncSession, target: Path, *, kind: BackupKind) -> dict[str, Any]:
    settings = get_settings()
    snapshot = await database_snapshot(db)
    database_bytes = json_payload(snapshot)
    checksums: dict[str, str] = {"database.json": hashlib.sha256(database_bytes).hexdigest()}
    files = list(
        await db.scalars(
            select(FileAsset).where(FileAsset.deleted_at.is_(None)).order_by(FileAsset.id)
        )
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    dump_path = target.with_suffix(".pgcustom")
    try:
        has_physical = await asyncio.to_thread(create_postgres_dump, dump_path)
        with zipfile.ZipFile(
            target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as archive:
            archive.writestr("database.json", database_bytes)
            if has_physical:
                checksums["database.pgcustom"] = sha256_file(dump_path)
                archive.write(dump_path, "database.pgcustom")
            for asset in files:
                for relative in (asset.stored_path, asset.thumbnail_path):
                    if not relative:
                        continue
                    source = settings.files_dir / relative
                    if not source.is_file():
                        raise ArchiveError(f"Отсутствует связанный файл {asset.id}")
                    member = f"files/{relative}"
                    checksums[member] = sha256_file(source)
                    archive.write(source, member)
            version = await schema_version(db)
            manifest = {
                "format": 1,
                "kind": kind,
                "created_at": now_utc().isoformat(),
                "month": now_utc().strftime("%Y-%m"),
                "app_version": APP_VERSION,
                "schema_version": version,
                "table_counts": {name: len(rows) for name, rows in snapshot["tables"].items()},
                "file_assets": len(files),
                "physical_database": has_physical,
                "checksums": checksums,
            }
            archive.writestr("manifest.json", json_payload(manifest))
    finally:
        dump_path.unlink(missing_ok=True)
    return verify_archive(target)


async def restore_physical_database(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        if "database.pgcustom" not in archive.namelist():
            return False
        descriptor, raw = tempfile.mkstemp(prefix="domovoy-restore-", suffix=".pgcustom")
        os.close(descriptor)
        temporary = Path(raw)
        try:
            await asyncio.to_thread(extract_postgres_dump, path, temporary)
            return await asyncio.to_thread(restore_postgres_dump, temporary)
        finally:
            temporary.unlink(missing_ok=True)  # noqa: ASYNC240


async def create_archive(
    db: AsyncSession,
    *,
    household_id: str,
    created_by_id: str | None,
    kind: BackupKind,
) -> BackupArchive:
    settings = get_settings()
    identifier = new_id()
    if kind == "monthly":
        relative = Path("monthly") / "domovoy-monthly.zip"
    else:
        stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
        relative = Path(kind) / f"domovoy-{kind}-{stamp}-{identifier}.zip"
    final_path = settings.backups_dir / relative
    final_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        prefix=".building-", suffix=".zip", dir=final_path.parent
    )
    os.close(descriptor)
    temporary = Path(raw_temp)
    try:
        manifest = await build_archive(db, temporary, kind=kind)
        archive_checksum = sha256_file(temporary)
        size = temporary.stat().st_size  # noqa: ASYNC240
        os.replace(temporary, final_path)
    except Exception:
        temporary.unlink(missing_ok=True)  # noqa: ASYNC240
        raise

    existing = None
    if kind == "monthly":
        existing = await db.scalar(
            select(BackupArchive).where(
                BackupArchive.household_id == household_id,
                BackupArchive.kind == "monthly",
            )
        )
    if existing is None:
        existing = BackupArchive(
            id=identifier,
            household_id=household_id,
            created_by_id=created_by_id,
            kind=kind,
            path=relative.as_posix(),
            checksum=archive_checksum,
            size_bytes=size,
            app_version=APP_VERSION,
            schema_version=str(manifest["schema_version"]),
            status="verified",
            manifest=manifest,
            verified_at=now_utc(),
        )
        db.add(existing)
    else:
        existing.created_by_id = created_by_id
        existing.path = relative.as_posix()
        existing.checksum = archive_checksum
        existing.size_bytes = size
        existing.app_version = APP_VERSION
        existing.schema_version = str(manifest["schema_version"])
        existing.status = "verified"
        existing.manifest = manifest
        existing.verified_at = now_utc()
        existing.updated_at = now_utc()
    await db.flush()
    return existing


async def create_monthly_if_due(db: AsyncSession) -> bool:
    household_id = await db.scalar(text("SELECT id FROM households LIMIT 1"))
    if not household_id:
        return False
    existing = await db.scalar(
        select(BackupArchive).where(
            BackupArchive.household_id == household_id,
            BackupArchive.kind == "monthly",
        )
    )
    month = now_utc().strftime("%Y-%m")
    if existing is not None and existing.manifest.get("month") == month:
        return False
    await create_archive(
        db,
        household_id=str(household_id),
        created_by_id=None,
        kind="monthly",
    )
    return True


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def archive_database(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = verify_archive(path)
    archive_schema = str(manifest.get("schema_version"))
    if archive_schema not in SCHEMA_ORDER or SCHEMA_ORDER.index(
        archive_schema
    ) > SCHEMA_ORDER.index(CURRENT_SCHEMA):
        raise ArchiveError("Архив создан более новой несовместимой версией")
    with zipfile.ZipFile(path) as archive:
        database = json.loads(archive.read("database.json"))
    return manifest, database


async def current_counts(db: AsyncSession) -> dict[str, int]:
    result: dict[str, int] = {}
    for table in backup_tables():
        result[table.name] = int(await db.scalar(select(func.count()).select_from(table)) or 0)
    return result


def ordered_rows(table_name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if table_name != "storage_nodes":
        return rows
    pending = list(rows)
    ordered: list[dict[str, Any]] = []
    known: set[str] = set()
    while pending:
        ready = [
            row for row in pending if row.get("parent_id") is None or row.get("parent_id") in known
        ]
        if not ready:
            raise ArchiveError("В дереве кладовой обнаружен цикл")
        for row in ready:
            ordered.append(row)
            known.add(str(row["id"]))
            pending.remove(row)
    return ordered


async def restore_database(db: AsyncSession, payload: dict[str, Any]) -> dict[str, int]:
    table_payload = payload.get("tables", {})
    known = {table.name: table for table in backup_tables()}
    unknown = set(table_payload) - set(known)
    if unknown:
        raise ArchiveError(f"Архив содержит неизвестные таблицы: {', '.join(sorted(unknown))}")
    for table in reversed(backup_tables()):
        await db.execute(delete(table))
    for table in backup_tables():
        rows = ordered_rows(table.name, list(table_payload.get(table.name, [])))
        for raw in rows:
            values = {
                column.name: decoded(column, raw[column.name])
                for column in table.columns
                if column.name in raw
            }
            await db.execute(insert(table).values(**values))
    revoked = now_utc()
    await db.execute(update(Session).values(revoked_at=revoked))
    await db.flush()
    return await current_counts(db)


def stage_files(path: Path, files_dir: Path) -> Path:
    stage = files_dir / f".restore-{new_id()}"
    stage.mkdir(parents=True, exist_ok=False)
    (stage / "objects").mkdir()
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.startswith("files/") or name.endswith("/"):
                    continue
                relative = PurePosixPath(name).relative_to("files")
                if ".." in relative.parts:
                    raise ArchiveError("Недопустимый путь файла")
                target = stage.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        return stage
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def swap_files(stage: Path, files_dir: Path) -> Path | None:
    current = files_dir / "objects"
    incoming = stage / "objects"
    previous_path = files_dir / f".previous-{new_id()}"
    if current.exists():
        os.replace(current, previous_path)
        previous: Path | None = previous_path
    else:
        previous = None
    os.replace(incoming, current)
    shutil.rmtree(stage, ignore_errors=True)
    return previous


def rollback_file_swap(previous: Path | None, files_dir: Path) -> None:
    current = files_dir / "objects"
    if current.exists():
        shutil.rmtree(current)
    if previous is not None and previous.exists():
        os.replace(previous, current)


def finalize_file_swap(previous: Path | None) -> None:
    if previous is not None:
        shutil.rmtree(previous, ignore_errors=True)
