from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    AuthContext,
    admin_auth,
    admin_csrf_auth,
    csrf_auth,
    current_auth,
)
from app.db.session import get_db_session
from app.models.home import MaintenanceRecord
from app.models.identity import User, UserRole
from app.models.lifecycle import TrashEntry
from app.models.shopping import ShoppingList
from app.models.storage import StorageItem
from app.models.tasks import TaskDefinition, TaskInstance
from app.schemas.common import Message
from app.schemas.lifecycle import ArchiveRead, TrashCreate, TrashRead
from app.services.auth import as_aware
from app.services.lifecycle import (
    permanently_delete_entry,
    restore_entry,
    trash_entity,
    unlink_purged_files,
)

router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])


def ensure_adult(auth: AuthContext) -> None:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(status_code=403, detail="Архив доступен взрослым")


@router.get("/archive", response_model=list[ArchiveRead])
async def archive(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[ArchiveRead]:
    ensure_adult(auth)
    household_id = auth.user.household_id
    trashed = {
        (entry.entity_type, entry.entity_id)
        for entry in await db.scalars(
            select(TrashEntry).where(TrashEntry.household_id == household_id)
        )
    }
    result: list[ArchiveRead] = []
    tasks = list(
        (
            await db.execute(
                select(TaskInstance, TaskDefinition)
                .join(TaskDefinition)
                .where(
                    TaskDefinition.household_id == household_id,
                    TaskInstance.status == "completed",
                )
            )
        ).all()
    )
    for instance, definition in tasks:
        if (
            definition.repeat_rule.get("kind", "none") == "none"
            and ("task", definition.id) not in trashed
        ):
            result.append(
                ArchiveRead(
                    entity_type="task",
                    entity_id=definition.id,
                    title=definition.title,
                    archived_at=instance.completed_at or instance.updated_at,
                    detail="Однократное дело выполнено",
                )
            )
    shopping_lists = list(
        await db.scalars(
            select(ShoppingList).where(
                ShoppingList.household_id == household_id,
                ShoppingList.status == "completed",
            )
        )
    )
    for shopping_list in shopping_lists:
        if ("shopping_list", shopping_list.id) not in trashed:
            result.append(
                ArchiveRead(
                    entity_type="shopping_list",
                    entity_id=shopping_list.id,
                    title=shopping_list.title,
                    archived_at=shopping_list.completed_at or shopping_list.updated_at,
                    detail="Покупка завершена",
                )
            )
    storage_items = list(
        await db.scalars(
            select(StorageItem).where(
                StorageItem.household_id == household_id,
                (StorageItem.archived_at.is_not(None))
                | (StorageItem.item_status.in_(["sold", "given", "discarded"])),
            )
        )
    )
    for storage_item in storage_items:
        if ("storage_item", storage_item.id) not in trashed:
            result.append(
                ArchiveRead(
                    entity_type="storage_item",
                    entity_id=storage_item.id,
                    title=storage_item.name,
                    archived_at=storage_item.archived_at or storage_item.updated_at,
                    detail=f"Статус: {storage_item.item_status}",
                )
            )
    users = list(
        await db.scalars(
            select(User).where(User.household_id == household_id, User.is_active.is_(False))
        )
    )
    for user in users:
        if ("user", user.id) not in trashed:
            result.append(
                ArchiveRead(
                    entity_type="user",
                    entity_id=user.id,
                    title=user.name,
                    archived_at=user.updated_at,
                    detail="Пользователь отключён",
                )
            )
    repairs = list(
        await db.scalars(
            select(MaintenanceRecord).where(MaintenanceRecord.household_id == household_id)
        )
    )
    for record in repairs:
        if ("repair", record.id) not in trashed:
            performed = datetime.combine(record.performed_on, datetime.min.time(), UTC)
            result.append(
                ArchiveRead(
                    entity_type="repair",
                    entity_id=record.id,
                    title=record.title,
                    archived_at=record.archived_at or performed,
                    detail="Запись обслуживания",
                )
            )
    return sorted(result, key=lambda item: as_aware(item.archived_at), reverse=True)[:2000]


@router.get("/trash", response_model=list[TrashRead])
async def trash(
    auth: Annotated[AuthContext, Depends(admin_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TrashEntry]:
    return list(
        await db.scalars(
            select(TrashEntry)
            .where(TrashEntry.household_id == auth.user.household_id)
            .order_by(TrashEntry.deleted_at.desc())
        )
    )


@router.post(
    "/trash/entities/{entity_type}/{entity_id}",
    response_model=TrashRead,
    status_code=status.HTTP_201_CREATED,
)
async def move_to_trash(
    entity_type: str,
    entity_id: str,
    payload: TrashCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TrashEntry:
    ensure_adult(auth)
    if entity_type == "user":
        if auth.user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Пользователя удаляет администратор")
        if entity_id == auth.user.id:
            raise HTTPException(status_code=409, detail="Нельзя удалить собственную учётную запись")
    entry = await trash_entity(
        db,
        household_id=auth.user.household_id,
        entity_type=entity_type,
        entity_id=entity_id,
        deleted_by_id=auth.user.id,
        file_action=payload.file_action,
    )
    await db.commit()
    await db.refresh(entry)
    return entry


async def load_trash_entry(db: AsyncSession, household_id: str, trash_id: str) -> TrashEntry:
    entry = await db.scalar(
        select(TrashEntry).where(TrashEntry.id == trash_id, TrashEntry.household_id == household_id)
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Запись корзины не найдена")
    return entry


@router.post("/trash/{trash_id}/restore", response_model=Message)
async def restore_from_trash(
    trash_id: str,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    entry = await load_trash_entry(db, auth.user.household_id, trash_id)
    await restore_entry(db, entry)
    await db.commit()
    return Message(message="Запись восстановлена")


@router.delete("/trash/{trash_id}", response_model=Message)
async def delete_forever(
    trash_id: str,
    auth: Annotated[AuthContext, Depends(admin_csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    entry = await load_trash_entry(db, auth.user.household_id, trash_id)
    paths = await permanently_delete_entry(db, entry)
    await db.commit()
    await unlink_purged_files(paths)
    return Message(message="Запись удалена безвозвратно")
