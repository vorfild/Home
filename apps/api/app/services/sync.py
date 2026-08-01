from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, cast

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.home import Equipment, MaintenancePlan, Meter
from app.models.identity import User, UserRole
from app.models.shopping import ShoppingItem, ShoppingList
from app.models.storage import StorageItem
from app.models.sync import EntityVersion, SyncConflict, SyncEvent, SyncOperation
from app.models.tasks import TaskDefinition
from app.schemas.sync import SyncChange, SyncChangeResult
from app.services.auth import now_utc
from app.services.notifications import create_notification


@dataclass(frozen=True)
class EntitySpec:
    model: type[Any]
    fields: frozenset[str]


SPECS: dict[str, EntitySpec] = {
    "task": EntitySpec(
        TaskDefinition,
        frozenset({"title", "description", "room", "category", "priority"}),
    ),
    "shopping_item": EntitySpec(
        ShoppingItem,
        frozenset({"name", "quantity", "unit", "category", "note", "purchased", "price", "store"}),
    ),
    "storage_item": EntitySpec(
        StorageItem,
        frozenset({"name", "category", "description", "tags", "item_status", "comment"}),
    ),
    "equipment": EntitySpec(
        Equipment,
        frozenset({"name", "category", "location", "condition"}),
    ),
    "maintenance": EntitySpec(
        MaintenancePlan,
        frozenset({"title", "checklist", "materials"}),
    ),
    "meter": EntitySpec(
        Meter,
        frozenset({"meter_type", "unit", "serial_number", "location"}),
    ),
}


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    return value


async def load_entity(
    db: AsyncSession, entity_type: str, entity_id: str, household_id: str
) -> tuple[Any, EntitySpec]:
    spec = SPECS.get(entity_type)
    if spec is None:
        raise HTTPException(status_code=422, detail="Этот тип записи не поддерживает синхронизацию")
    if entity_type == "shopping_item":
        entity = await db.scalar(
            select(ShoppingItem)
            .join(ShoppingList)
            .where(ShoppingItem.id == entity_id, ShoppingList.household_id == household_id)
        )
    else:
        entity = await db.scalar(
            select(spec.model).where(
                spec.model.id == entity_id, spec.model.household_id == household_id
            )
        )
    if entity is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return entity, spec


def entity_state(entity: Any, spec: EntitySpec) -> dict[str, Any]:
    return {field: json_value(getattr(entity, field)) for field in sorted(spec.fields)}


async def version_for(
    db: AsyncSession,
    *,
    household_id: str,
    entity_type: str,
    entity_id: str,
    entity: Any,
    spec: EntitySpec,
    lock: bool = False,
) -> EntityVersion:
    query = select(EntityVersion).where(
        EntityVersion.household_id == household_id,
        EntityVersion.entity_type == entity_type,
        EntityVersion.entity_id == entity_id,
    )
    if lock:
        query = query.with_for_update()
    item = await db.scalar(query)
    if item is None:
        state = entity_state(entity, spec)
        item = EntityVersion(
            household_id=household_id,
            entity_type=entity_type,
            entity_id=entity_id,
            version=1,
            state=state,
            field_versions={field: 1 for field in state},
        )
        db.add(item)
        await db.flush()
    return item


def converted_value(entity_type: str, field: str, value: Any) -> Any:
    if field in {"quantity", "price"}:
        return Decimal(str(value)) if value not in (None, "") else None
    if field == "purchased":
        return bool(value)
    if field in {"tags", "checklist", "materials"}:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise HTTPException(status_code=422, detail=f"Поле {field} должно быть списком строк")
        return value
    if value is not None and not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"Поле {field} должно быть строкой")
    if isinstance(value, str):
        value = value.strip()
    if field in {"title", "name", "meter_type", "unit"} and not value:
        raise HTTPException(status_code=422, detail=f"Поле {field} не может быть пустым")
    return value


def apply_fields(entity_type: str, entity: Any, changes: dict[str, Any]) -> None:
    for field, raw in changes.items():
        value = converted_value(entity_type, field, raw)
        setattr(entity, field, value)
        if field == "name" and hasattr(entity, "normalized_name") and isinstance(value, str):
            entity.normalized_name = value.casefold()


async def record_sync_event(
    db: AsyncSession,
    *,
    household_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_id: str | None,
    changed_fields: list[str] | None = None,
    version: int | None = None,
) -> SyncEvent:
    item = SyncEvent(
        household_id=household_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_id=actor_id,
        changed_fields=changed_fields or [],
        version=version,
        created_at=now_utc(),
    )
    db.add(item)
    await db.flush()
    return item


async def maybe_notify_conflict_threshold(db: AsyncSession, household_id: str) -> None:
    count = int(
        await db.scalar(
            select(func.count(SyncConflict.id)).where(
                SyncConflict.household_id == household_id,
                SyncConflict.status == "pending",
            )
        )
        or 0
    )
    if count < 5:
        return
    admins = await db.scalars(
        select(User).where(
            User.household_id == household_id,
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
        )
    )
    for admin in admins:
        await create_notification(
            db,
            household_id=household_id,
            user_id=admin.id,
            event_type="sync_conflicts",
            title="Конфликты синхронизации",
            body=f"Нужно разобрать конфликтующие изменения: {count}",
            source_type="sync_conflicts",
            source_id=household_id,
            marker="five-unresolved",
        )


async def apply_sync_change(
    db: AsyncSession, *, household_id: str, user_id: str, payload: SyncChange
) -> SyncChangeResult:
    previous = await db.scalar(
        select(SyncOperation).where(
            SyncOperation.client_operation_id == payload.client_operation_id
        )
    )
    entity, spec = await load_entity(db, payload.entity_type, payload.entity_id, household_id)
    version = await version_for(
        db,
        household_id=household_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity=entity,
        spec=spec,
        lock=True,
    )
    if previous is not None:
        conflicts = list(
            await db.scalars(
                select(SyncConflict.id).where(
                    SyncConflict.proposed_by_id == user_id,
                    SyncConflict.entity_type == payload.entity_type,
                    SyncConflict.entity_id == payload.entity_id,
                    SyncConflict.base_version == payload.base_version,
                )
            )
        )
        return SyncChangeResult(
            status=cast(Literal["applied", "merged", "conflict"], previous.result_status),
            version=previous.result_version,
            state=version.state,
            conflict_ids=conflicts,
        )
    unknown = set(payload.changes) - spec.fields
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Нельзя менять поля: {', '.join(sorted(unknown))}"
        )
    if payload.base_version > version.version:
        raise HTTPException(status_code=409, detail="Версия клиента новее серверной")

    safe: dict[str, Any] = {}
    conflicting: dict[str, Any] = {}
    for field, value in payload.changes.items():
        if int(version.field_versions.get(field, 1)) <= payload.base_version:
            safe[field] = value
        else:
            conflicting[field] = value

    conflict_ids: list[str] = []
    for field, value in conflicting.items():
        conflict = SyncConflict(
            household_id=household_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            field_name=field,
            base_version=payload.base_version,
            server_version=version.version,
            server_value=version.state.get(field),
            alternative_value=json_value(value),
            proposed_by_id=user_id,
            status="pending",
        )
        db.add(conflict)
        await db.flush()
        conflict_ids.append(conflict.id)

    if safe:
        apply_fields(payload.entity_type, entity, safe)
        version.version += 1
        state = dict(version.state)
        state.update({field: json_value(getattr(entity, field)) for field in safe})
        field_versions = dict(version.field_versions)
        field_versions.update({field: version.version for field in safe})
        version.state = state
        version.field_versions = field_versions
        version.last_actor_id = user_id
        await record_sync_event(
            db,
            household_id=household_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            action="merged" if conflicting else "updated",
            actor_id=user_id,
            changed_fields=sorted(safe),
            version=version.version,
        )
    result_status: Literal["applied", "merged", "conflict"] = (
        "conflict"
        if conflicting
        else ("merged" if payload.base_version < version.version - 1 else "applied")
    )
    db.add(
        SyncOperation(
            client_operation_id=payload.client_operation_id,
            user_id=user_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            base_version=payload.base_version,
            changes=json_value(payload.changes),
            result_status=result_status,
            result_version=version.version,
            created_at=now_utc(),
        )
    )
    if conflicting:
        await maybe_notify_conflict_threshold(db, household_id)
    return SyncChangeResult(
        status=result_status,
        version=version.version,
        state=version.state,
        conflict_ids=conflict_ids,
    )
