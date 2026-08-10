from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageOps
from pillow_heif import register_heif_opener  # type: ignore[import-untyped]
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.files import FileAsset
from app.models.home import Equipment, MaintenancePlan, MaintenanceRecord, Meter, MeterReading
from app.models.identity import User, UserRole, new_id
from app.models.shopping import ShoppingItem, ShoppingList
from app.models.storage import StorageItem
from app.models.tasks import TaskDefinition, TaskInstance
from app.services.auth import now_utc

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 50_000_000

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
ALLOWED_MIMES = IMAGE_MIMES | {"application/pdf"}
EXTENSIONS = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".heic": {"image/heic", "image/heif"},
    ".heif": {"image/heic", "image/heif"},
    ".pdf": {"application/pdf"},
}


def safe_name(value: str) -> str:
    name = Path(value).name.strip().replace("\x00", "")
    if not name or len(name) > 255:
        raise HTTPException(status_code=422, detail="Некорректное имя файла")
    return name


def detected_mime(path: Path) -> str | None:
    head = path.read_bytes()[:32]
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if (
        len(head) >= 12
        and head[4:8] == b"ftyp"
        and head[8:12]
        in {
            b"heic",
            b"heix",
            b"hevc",
            b"hevx",
            b"mif1",
            b"msf1",
        }
    ):
        return "image/heic"
    return None


def validate_upload(path: Path, filename: str, content_type: str) -> str:
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл должен быть не больше 25 МБ")
    extension = Path(filename).suffix.casefold()
    detected = detected_mime(path)
    if content_type not in ALLOWED_MIMES or detected not in ALLOWED_MIMES:
        raise HTTPException(status_code=415, detail="Разрешены JPG, PNG, WebP, HEIC и PDF")
    if extension not in EXTENSIONS or detected not in EXTENSIONS[extension]:
        raise HTTPException(status_code=415, detail="Расширение не соответствует содержимому")
    if content_type in {"image/heif", "image/heic"} and detected == "image/heic":
        return detected
    if content_type != detected:
        raise HTTPException(status_code=415, detail="MIME-тип не соответствует содержимому")
    return detected


async def ensure_entity_access(
    db: AsyncSession,
    *,
    household_id: str,
    user: User,
    entity_type: str,
    entity_id: str,
) -> Any:
    entity: Any | None = None
    if user.role == UserRole.CHILD and entity_type not in {
        "task_instance",
        "shopping_item",
        "profile",
    }:
        raise HTTPException(status_code=403, detail="Нет права прикреплять файл к этой записи")
    if entity_type == "task_instance":
        entity = await db.scalar(
            select(TaskInstance)
            .join(TaskDefinition)
            .where(TaskInstance.id == entity_id, TaskDefinition.household_id == household_id)
        )
        if entity is not None and user.role == UserRole.CHILD:
            task = await db.scalar(
                select(TaskDefinition).where(TaskDefinition.id == entity.task_id)
            )
            if task is None or not (
                task.assignment_mode == "anyone" or entity.assignee_id == user.id
            ):
                raise HTTPException(status_code=403, detail="Нет права прикреплять файл")
    elif entity_type == "shopping_item":
        entity = await db.scalar(
            select(ShoppingItem)
            .join(ShoppingList)
            .where(ShoppingItem.id == entity_id, ShoppingList.household_id == household_id)
        )
        if entity is not None and user.role == UserRole.CHILD and entity.added_by_id != user.id:
            raise HTTPException(status_code=403, detail="Нет права прикреплять файл")
    elif entity_type == "storage_item":
        entity = await db.scalar(
            select(StorageItem).where(
                StorageItem.id == entity_id, StorageItem.household_id == household_id
            )
        )
    elif entity_type == "equipment":
        entity = await db.scalar(
            select(Equipment).where(
                Equipment.id == entity_id, Equipment.household_id == household_id
            )
        )
    elif entity_type == "maintenance":
        entity = await db.scalar(
            select(MaintenancePlan).where(
                MaintenancePlan.id == entity_id,
                MaintenancePlan.household_id == household_id,
            )
        )
    elif entity_type == "repair":
        entity = await db.scalar(
            select(MaintenanceRecord).where(
                MaintenanceRecord.id == entity_id,
                MaintenanceRecord.household_id == household_id,
            )
        )
    elif entity_type == "meter_reading":
        entity = await db.scalar(
            select(MeterReading)
            .join(Meter)
            .where(MeterReading.id == entity_id, Meter.household_id == household_id)
        )
    elif entity_type == "profile":
        entity = await db.scalar(
            select(User).where(User.id == entity_id, User.household_id == household_id)
        )
        if user.role == UserRole.CHILD and entity_id != user.id:
            raise HTTPException(status_code=403, detail="Нет права прикреплять файл")
    if entity is None:
        raise HTTPException(status_code=404, detail="Связанная запись не найдена")
    return entity


def add_file_reference(entity: Any, asset_id: str, purpose: str, primary: bool) -> None:
    if purpose == "document" and hasattr(entity, "document_ids"):
        entity.document_ids = list(dict.fromkeys([*entity.document_ids, asset_id]))
    elif purpose == "attachment" and hasattr(entity, "attachment_ids"):
        entity.attachment_ids = list(dict.fromkeys([*entity.attachment_ids, asset_id]))
    elif hasattr(entity, "photo_ids"):
        entity.photo_ids = list(dict.fromkeys([*entity.photo_ids, asset_id]))
        if primary and hasattr(entity, "primary_photo_id"):
            entity.primary_photo_id = asset_id


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def store_file(
    source: Path,
    *,
    files_dir: Path,
    household_id: str,
    original_name: str,
    original_mime: str,
) -> dict[str, Any]:
    file_id = new_id()
    relative_dir = Path("objects") / household_id / file_id[:2]
    target_dir = files_dir / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    width: int | None = None
    height: int | None = None
    thumbnail_path: str | None = None
    if original_mime in IMAGE_MIMES:
        stored_relative = relative_dir / f"{file_id}.webp"
        thumb_relative = relative_dir / f"{file_id}.thumb.webp"
        stored = files_dir / stored_relative
        thumbnail = files_dir / thumb_relative
        stored_tmp = stored.with_suffix(".tmp")
        thumb_tmp = thumbnail.with_suffix(".tmp")
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
                if image.width * image.height > 50_000_000:
                    raise HTTPException(status_code=413, detail="Изображение слишком большое")
                image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
                width, height = image.size
                mode = "RGBA" if "A" in image.getbands() else "RGB"
                normalized = image.convert(mode)
                normalized.save(stored_tmp, "WEBP", quality=82, method=6)
                preview = normalized.copy()
                preview.thumbnail((480, 480), Image.Resampling.LANCZOS)
                preview.save(thumb_tmp, "WEBP", quality=74, method=6)
            os.replace(stored_tmp, stored)
            os.replace(thumb_tmp, thumbnail)
        except HTTPException:
            stored_tmp.unlink(missing_ok=True)
            thumb_tmp.unlink(missing_ok=True)
            raise
        except Exception as exc:
            stored_tmp.unlink(missing_ok=True)
            thumb_tmp.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail="Не удалось прочитать изображение") from exc
        stored_mime = "image/webp"
        thumbnail_path = thumb_relative.as_posix()
    else:
        stored_relative = relative_dir / f"{file_id}.pdf"
        thumb_relative = relative_dir / f"{file_id}.thumb.webp"
        stored = files_dir / stored_relative
        thumbnail = files_dir / thumb_relative
        stored_tmp = stored.with_suffix(".tmp")
        thumb_tmp = thumbnail.with_suffix(".tmp")
        shutil.copyfile(source, stored_tmp)
        preview = Image.new("RGB", (320, 420), "#f5f6f3")
        canvas = ImageDraw.Draw(preview)
        canvas.rounded_rectangle((70, 70, 250, 350), radius=12, fill="#ffffff", outline="#b54747")
        canvas.text((132, 192), "PDF", fill="#b54747", stroke_width=1)
        preview.save(thumb_tmp, "WEBP", quality=74, method=6)
        os.replace(stored_tmp, stored)
        os.replace(thumb_tmp, thumbnail)
        stored_mime = "application/pdf"
        thumbnail_path = thumb_relative.as_posix()
    return {
        "id": file_id,
        "original_name": original_name,
        "original_mime": original_mime,
        "stored_mime": stored_mime,
        "stored_path": stored_relative.as_posix(),
        "thumbnail_path": thumbnail_path,
        "checksum": sha256_file(stored),
        "size_bytes": stored.stat().st_size,
        "width": width,
        "height": height,
    }


async def register_asset(
    db: AsyncSession,
    *,
    household_id: str,
    user: User,
    entity_type: str,
    entity_id: str,
    purpose: str,
    primary: bool,
    stored: dict[str, Any],
) -> FileAsset:
    entity = await ensure_entity_access(
        db,
        household_id=household_id,
        user=user,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    existing = await db.scalar(
        select(FileAsset.id).where(
            FileAsset.household_id == household_id,
            FileAsset.entity_type == entity_type,
            FileAsset.entity_id == entity_id,
            FileAsset.purpose == purpose,
            FileAsset.deleted_at.is_(None),
        )
    )
    is_primary = primary or existing is None
    if is_primary:
        await db.execute(
            update(FileAsset)
            .where(
                FileAsset.household_id == household_id,
                FileAsset.entity_type == entity_type,
                FileAsset.entity_id == entity_id,
                FileAsset.purpose == purpose,
            )
            .values(is_primary=False)
        )
    asset = FileAsset(
        **stored,
        household_id=household_id,
        uploaded_by_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        purpose=purpose,
        is_primary=is_primary,
        created_at=now_utc(),
    )
    db.add(asset)
    add_file_reference(entity, asset.id, purpose, is_primary)
    return asset
