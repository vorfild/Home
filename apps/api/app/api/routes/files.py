from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.core.config import get_settings
from app.db.session import get_db_session
from app.models.files import FileAsset
from app.models.identity import UserRole
from app.schemas.common import Message
from app.schemas.files import FileRead
from app.services.auth import now_utc
from app.services.files import (
    MAX_UPLOAD_BYTES,
    ensure_entity_access,
    register_asset,
    safe_name,
    store_file,
    validate_upload,
)

router = APIRouter(prefix="/files", tags=["files"])
settings = get_settings()


async def load_asset(db: AsyncSession, household_id: str, asset_id: str) -> FileAsset:
    asset = await db.scalar(
        select(FileAsset).where(
            FileAsset.id == asset_id,
            FileAsset.household_id == household_id,
            FileAsset.deleted_at.is_(None),
        )
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return asset


async def ensure_asset_access(db: AsyncSession, auth: AuthContext, asset: FileAsset) -> None:
    if asset.entity_type == "preserved":
        if auth.user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Сохранённые файлы доступны администратору")
        return
    await ensure_entity_access(
        db,
        household_id=auth.user.household_id,
        user=auth.user,
        entity_type=asset.entity_type,
        entity_id=asset.entity_id,
    )


@router.post("", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    entity_type: str = Query(min_length=2, max_length=40),
    entity_id: str = Query(min_length=36, max_length=36),
    purpose: str = Query(default="attachment", pattern="^(photo|document|attachment|avatar)$"),
    primary: bool = False,
) -> FileAsset:
    filename = safe_name(unquote(request.headers.get("X-Filename", "")))
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0].casefold()
    length = request.headers.get("Content-Length")
    if length and int(length) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл должен быть не больше 25 МБ")
    settings.files_dir.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(prefix=".upload-", dir=settings.files_dir)
    temporary = Path(raw_path)
    total = 0
    stored: dict[str, Any] | None = None
    committed = False
    try:
        with os.fdopen(descriptor, "wb") as stream:
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Файл должен быть не больше 25 МБ")
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        detected = validate_upload(temporary, filename, content_type)
        if purpose in {"photo", "avatar"} and not detected.startswith("image/"):
            raise HTTPException(status_code=415, detail="Для фотографии нужен файл изображения")
        await ensure_entity_access(
            db,
            household_id=auth.user.household_id,
            user=auth.user,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        stored = store_file(
            temporary,
            files_dir=settings.files_dir,
            household_id=auth.user.household_id,
            original_name=filename,
            original_mime=detected,
        )
        asset = await register_asset(
            db,
            household_id=auth.user.household_id,
            user=auth.user,
            entity_type=entity_type,
            entity_id=entity_id,
            purpose=purpose,
            primary=primary,
            stored=stored,
        )
        await db.commit()
        committed = True
        await db.refresh(asset)
        return asset
    finally:
        if stored is not None and not committed:
            for key in ("stored_path", "thumbnail_path"):
                relative = stored.get(key)
                if isinstance(relative, str):
                    (settings.files_dir / relative).unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)  # noqa: ASYNC240


@router.get("", response_model=list[FileRead])
async def list_files(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    entity_type: str,
    entity_id: str,
) -> list[FileAsset]:
    if entity_type == "preserved":
        if auth.user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Сохранённые файлы доступны администратору")
    else:
        await ensure_entity_access(
            db,
            household_id=auth.user.household_id,
            user=auth.user,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    return list(
        await db.scalars(
            select(FileAsset)
            .where(
                FileAsset.household_id == auth.user.household_id,
                FileAsset.entity_type == entity_type,
                FileAsset.entity_id == entity_id,
                FileAsset.deleted_at.is_(None),
            )
            .order_by(FileAsset.is_primary.desc(), FileAsset.created_at)
        )
    )


@router.get("/{asset_id}")
async def get_file(
    asset_id: str,
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    thumbnail: bool = False,
) -> FileResponse:
    asset = await load_asset(db, auth.user.household_id, asset_id)
    await ensure_asset_access(db, auth, asset)
    relative = asset.thumbnail_path if thumbnail and asset.thumbnail_path else asset.stored_path
    path = settings.files_dir / relative
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Файл отсутствует в хранилище")
    return FileResponse(
        path,
        media_type="image/webp" if thumbnail else asset.stored_mime,
        filename=None if asset.stored_mime.startswith("image/") else asset.original_name,
        headers={
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{asset.checksum}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{asset_id}/primary", response_model=FileRead)
async def make_primary(
    asset_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> FileAsset:
    asset = await load_asset(db, auth.user.household_id, asset_id)
    await ensure_asset_access(db, auth, asset)
    if auth.user.role == UserRole.CHILD and asset.uploaded_by_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Нет права менять этот файл")
    await db.execute(
        update(FileAsset)
        .where(
            FileAsset.household_id == asset.household_id,
            FileAsset.entity_type == asset.entity_type,
            FileAsset.entity_id == asset.entity_id,
            FileAsset.purpose == asset.purpose,
        )
        .values(is_primary=False)
    )
    asset.is_primary = True
    await db.commit()
    await db.refresh(asset)
    return asset


@router.delete("/{asset_id}", response_model=Message)
async def delete_file(
    asset_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    asset = await load_asset(db, auth.user.household_id, asset_id)
    await ensure_asset_access(db, auth, asset)
    if auth.user.role == UserRole.CHILD and asset.uploaded_by_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Нет права удалить этот файл")
    asset.deleted_at = now_utc()
    await db.commit()
    for relative in (asset.stored_path, asset.thumbnail_path):
        if relative:
            (settings.files_dir / relative).unlink(missing_ok=True)
    return Message(message="Файл удалён")
