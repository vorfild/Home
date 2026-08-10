from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.files import FileAsset
from app.models.home import Equipment, MaintenanceRecord
from app.models.identity import Session, User
from app.models.lifecycle import TrashEntry
from app.models.shopping import ShoppingItem, ShoppingList
from app.models.storage import StorageItem, StorageNode
from app.models.tasks import TaskDefinition, TaskInstance
from app.services.auth import now_utc

ENTITY_TYPES = {"task", "shopping_list", "storage_item", "user", "equipment", "repair"}


@dataclass(frozen=True)
class TrashPurgeResult:
    count: int
    paths: tuple[Path, ...]


async def load_entity(db: AsyncSession, household_id: str, entity_type: str, entity_id: str) -> Any:
    model: type[Any]
    if entity_type == "task":
        model = TaskDefinition
    elif entity_type == "shopping_list":
        model = ShoppingList
    elif entity_type == "storage_item":
        model = StorageItem
    elif entity_type == "user":
        model = User
    elif entity_type == "equipment":
        model = Equipment
    elif entity_type == "repair":
        model = MaintenanceRecord
    else:
        raise HTTPException(status_code=422, detail="Этот тип записи нельзя удалить")
    entity = await db.scalar(
        select(model).where(model.id == entity_id, model.household_id == household_id)
    )
    if entity is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return entity


async def trash_entity(
    db: AsyncSession,
    *,
    household_id: str,
    entity_type: str,
    entity_id: str,
    deleted_by_id: str,
    file_action: str,
) -> TrashEntry:
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="Этот тип записи нельзя удалить")
    duplicate = await db.scalar(
        select(TrashEntry.id).where(
            TrashEntry.household_id == household_id,
            TrashEntry.entity_type == entity_type,
            TrashEntry.entity_id == entity_id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Запись уже находится в корзине")
    entity = await load_entity(db, household_id, entity_type, entity_id)
    previous: dict[str, Any] = {}
    now = now_utc()
    if entity_type == "task":
        previous["is_active"] = entity.is_active
        entity.is_active = False
        title = entity.title
    elif entity_type == "shopping_list":
        previous["archived_at"] = entity.archived_at.isoformat() if entity.archived_at else None
        entity.archived_at = now
        title = entity.title
    elif entity_type == "storage_item":
        previous["archived_at"] = entity.archived_at.isoformat() if entity.archived_at else None
        entity.archived_at = now
        title = entity.name
    elif entity_type == "user":
        previous["is_active"] = entity.is_active
        entity.is_active = False
        await db.execute(
            update(Session)
            .where(Session.user_id == entity.id, Session.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        title = entity.name
    elif entity_type == "equipment":
        previous["archived_at"] = entity.archived_at.isoformat() if entity.archived_at else None
        entity.archived_at = now
        title = entity.name or "Техника"
    else:
        previous["archived_at"] = entity.archived_at.isoformat() if entity.archived_at else None
        entity.archived_at = now
        title = entity.title
    entry = TrashEntry(
        household_id=household_id,
        entity_type=entity_type,
        entity_id=entity_id,
        title=title,
        deleted_by_id=deleted_by_id,
        deleted_at=now,
        purge_after=now + timedelta(days=30),
        file_action=file_action,
        previous_state=previous,
    )
    db.add(entry)
    await db.flush()
    return entry


async def restore_entry(db: AsyncSession, entry: TrashEntry) -> None:
    if entry.entity_type == "storage_node":
        node_ids = entry.previous_state.get("node_ids", [entry.entity_id])
        nodes = list(await db.scalars(select(StorageNode).where(StorageNode.id.in_(node_ids))))
        for node in nodes:
            node.deleted_at = None
            node.purge_after = None
    else:
        entity = await load_entity(db, entry.household_id, entry.entity_type, entry.entity_id)
        if entry.entity_type in {"task", "user"}:
            entity.is_active = bool(entry.previous_state.get("is_active", True))
        else:
            entity.archived_at = None
    await db.delete(entry)


async def associated_file_refs(db: AsyncSession, entry: TrashEntry) -> list[tuple[str, str]]:
    refs = [(entry.entity_type, entry.entity_id)]
    if entry.entity_type == "task":
        ids = list(
            await db.scalars(select(TaskInstance.id).where(TaskInstance.task_id == entry.entity_id))
        )
        refs.extend(("task_instance", item_id) for item_id in ids)
    elif entry.entity_type == "shopping_list":
        ids = list(
            await db.scalars(select(ShoppingItem.id).where(ShoppingItem.list_id == entry.entity_id))
        )
        refs.extend(("shopping_item", item_id) for item_id in ids)
    elif entry.entity_type == "storage_node":
        ids = entry.previous_state.get("item_ids", [])
        refs.extend(("storage_item", item_id) for item_id in ids)
    elif entry.entity_type == "repair":
        refs.append(("maintenance_record", entry.entity_id))
    return refs


async def handle_entry_files(db: AsyncSession, entry: TrashEntry) -> list[Path]:
    refs = await associated_file_refs(db, entry)
    conditions = [
        (FileAsset.entity_type == entity_type) & (FileAsset.entity_id == entity_id)
        for entity_type, entity_id in refs
    ]
    if not conditions:
        return []
    from sqlalchemy import or_

    assets = list(
        await db.scalars(
            select(FileAsset).where(
                FileAsset.household_id == entry.household_id,
                or_(*conditions),
                FileAsset.deleted_at.is_(None),
            )
        )
    )
    if entry.file_action == "keep":
        for asset in assets:
            asset.entity_type = "preserved"
            asset.entity_id = entry.id
        return []
    settings = get_settings()
    paths: list[Path] = []
    for asset in assets:
        asset.deleted_at = now_utc()
        paths.append(settings.files_dir / asset.stored_path)
        if asset.thumbnail_path:
            paths.append(settings.files_dir / asset.thumbnail_path)
    return paths


async def permanently_delete_entry(db: AsyncSession, entry: TrashEntry) -> list[Path]:
    paths = await handle_entry_files(db, entry)
    if entry.entity_type == "storage_node":
        node_ids = entry.previous_state.get("node_ids", [entry.entity_id])
        await db.execute(delete(StorageNode).where(StorageNode.id.in_(node_ids)))
    else:
        entity = await load_entity(db, entry.household_id, entry.entity_type, entry.entity_id)
        await db.delete(entity)
    await db.delete(entry)
    return paths


async def purge_expired_trash(db: AsyncSession) -> TrashPurgeResult:
    entries = list(await db.scalars(select(TrashEntry).where(TrashEntry.purge_after <= now_utc())))
    paths: list[Path] = []
    for entry in entries:
        paths.extend(await permanently_delete_entry(db, entry))
    return TrashPurgeResult(count=len(entries), paths=tuple(paths))


async def unlink_purged_files(paths: tuple[Path, ...] | list[Path]) -> None:
    await asyncio.gather(*(asyncio.to_thread(path.unlink, missing_ok=True) for path in paths))
