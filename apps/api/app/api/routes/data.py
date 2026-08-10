from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, admin_auth, admin_csrf_auth
from app.core.config import get_settings
from app.core.security import verify_secret
from app.db.session import get_db_session
from app.models.files import BackupArchive, RestoreReport
from app.models.identity import User
from app.schemas.files import BackupRead, DataStatus, RestoreRead, UpdatePlan, UpdatePrepare
from app.services.auth import now_utc
from app.services.backups import (
    APP_VERSION,
    CURRENT_SCHEMA,
    MAX_ARCHIVE_BYTES,
    ArchiveError,
    archive_database,
    create_archive,
    current_counts,
    directory_size,
    finalize_file_swap,
    restore_database,
    rollback_file_swap,
    stage_files,
    swap_files,
)

router = APIRouter(prefix="/data", tags=["data"])
settings = get_settings()


async def backup_for(db: AsyncSession, household_id: str, backup_id: str) -> BackupArchive:
    item = await db.scalar(
        select(BackupArchive).where(
            BackupArchive.id == backup_id,
            BackupArchive.household_id == household_id,
            BackupArchive.status == "verified",
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Архив не найден")
    return item


@router.get("/status", response_model=DataStatus)
async def data_status(
    auth: Annotated[AuthContext, Depends(admin_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> DataStatus:
    items = list(
        await db.scalars(
            select(BackupArchive)
            .where(BackupArchive.household_id == auth.user.household_id)
            .order_by(BackupArchive.created_at.desc())
        )
    )
    monthly = next((item for item in items if item.kind == "monthly"), None)
    return DataStatus(
        monthly=BackupRead.model_validate(monthly) if monthly else None,
        manual=[BackupRead.model_validate(item) for item in items if item.kind == "manual"],
        insurance=[BackupRead.model_validate(item) for item in items if item.kind == "insurance"][
            :10
        ],
        files_bytes=directory_size(settings.files_dir),
        backups_bytes=directory_size(settings.backups_dir),
        app_version=APP_VERSION,
        schema_version=CURRENT_SCHEMA,
    )


@router.post("/exports", response_model=BackupRead, status_code=status.HTTP_201_CREATED)
async def manual_export(
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BackupArchive:
    try:
        item = await create_archive(
            db,
            household_id=auth.user.household_id,
            created_by_id=auth.user.id,
            kind="manual",
        )
        await db.commit()
        await db.refresh(item)
        return item
    except ArchiveError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/backups/{backup_id}/download")
async def download_backup(
    backup_id: str,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> FileResponse:
    item = await backup_for(db, auth.user.household_id, backup_id)
    path = settings.backups_dir / item.path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл архива отсутствует")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=Path(item.path).name,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/imports", response_model=RestoreRead, status_code=status.HTTP_201_CREATED)
async def import_archive(
    request: Request,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RestoreReport:
    password = request.headers.get("X-Domovoy-Admin-Password", "")
    if not verify_secret(password, auth.user.password_hash):
        raise HTTPException(status_code=403, detail="Неверный пароль администратора")
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0]
    if content_type not in {"application/zip", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Нужен ZIP-архив Домового")
    source_name = Path(unquote(request.headers.get("X-Filename", "domovoy-import.zip"))).name
    incoming_dir = settings.backups_dir / "incoming"
    incoming_dir.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix="import-", suffix=".zip", dir=incoming_dir)
    incoming = Path(raw_path)
    total = 0
    stage: Path | None = None
    previous: Path | None = None
    swapped = False
    actor_id = auth.user.id
    old_household_id = auth.user.household_id
    try:
        with os.fdopen(descriptor, "wb") as stream:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise HTTPException(status_code=413, detail="Архив слишком большой")
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            manifest, database = archive_database(incoming)
        except ArchiveError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        insurance = await create_archive(
            db,
            household_id=old_household_id,
            created_by_id=actor_id,
            kind="insurance",
        )
        await db.commit()
        insurance_path = insurance.path
        counts_before = await current_counts(db)
        stage = stage_files(incoming, settings.files_dir)
        counts_after = await restore_database(db, database)
        expected = manifest.get("table_counts", {})
        mismatches = [
            name
            for name, count in expected.items()
            if name in counts_after and counts_after[name] != count
        ]
        if mismatches:
            raise ArchiveError(f"Не совпало количество записей: {', '.join(mismatches)}")
        previous = swap_files(stage, settings.files_dir)
        swapped = True
        await db.commit()
        finalize_file_swap(previous)
        previous = None

        household_rows = database["tables"].get("households", [])
        if not household_rows:
            raise ArchiveError("В архиве отсутствует семья")
        household_id = str(household_rows[0]["id"])
        imported_actor = await db.scalar(select(User.id).where(User.id == actor_id))
        report = RestoreReport(
            household_id=household_id,
            performed_by_id=str(imported_actor) if imported_actor else None,
            source_name=source_name,
            source_checksum=str(manifest.get("checksums", {}).get("database.json", "")),
            status="completed",
            counts_before=counts_before,
            counts_after=counts_after,
            warnings=[
                f"Страховочная копия: {insurance_path}",
                "Все активные сессии аннулированы; войдите снова.",
            ],
            details="Файлы и стабильные QR восстановлены, контрольные суммы проверены.",
            created_at=now_utc(),
            completed_at=now_utc(),
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)
        request.state.sync_event_recorded = True
        return report
    except HTTPException:
        await db.rollback()
        if swapped:
            rollback_file_swap(previous, settings.files_dir)
        elif stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        raise
    except (ArchiveError, OSError, SQLAlchemyError) as exc:
        await db.rollback()
        if swapped:
            rollback_file_swap(previous, settings.files_dir)
        elif stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"Импорт отменён: {exc}") from exc
    finally:
        incoming.unlink(missing_ok=True)  # noqa: ASYNC240


@router.get("/updates/status")
async def update_status(
    _: Annotated[AuthContext, Depends(admin_auth)],
) -> dict[str, object]:
    state = Path(".domovoy-update-state")
    return {
        "current_version": APP_VERSION,
        "automatic_execution": False,
        "rollback_available": state.is_file(),  # noqa: ASYNC240
        "update_command": "./scripts/update-server.sh <tag-or-commit>",
        "reason": "Обновление запускается в SSH-сессии, чтобы пережить перезапуск контейнера.",
    }


@router.post("/updates/prepare", response_model=UpdatePlan)
async def prepare_update(
    payload: UpdatePrepare,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> UpdatePlan:
    if not verify_secret(payload.password, auth.user.password_hash):
        raise HTTPException(status_code=403, detail="Неверный пароль администратора")
    insurance = await create_archive(
        db,
        household_id=auth.user.household_id,
        created_by_id=auth.user.id,
        kind="insurance",
    )
    await db.commit()
    return UpdatePlan(
        current_version=APP_VERSION,
        target_ref=payload.target_ref,
        insurance_backup_id=insurance.id,
        command=f"./scripts/update-server.sh {payload.target_ref}",
        rollback_command="./scripts/rollback-server.sh",
    )
