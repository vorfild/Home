from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.db.session import get_db_session
from app.models.home import Equipment, MaintenancePlan, Meter
from app.models.identity import Household, UserRole
from app.models.shopping import ShoppingList
from app.models.storage import StorageItem
from app.models.tasks import TaskAssignment, TaskDefinition, TaskInstance
from app.schemas.calendar import CalendarEvent, CalendarMove
from app.schemas.common import Message

router = APIRouter(prefix="/calendar", tags=["calendar"])


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="Дата должна содержать часовой пояс")
    return value.astimezone(UTC)


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def date_at_noon(value: date, timezone: ZoneInfo) -> datetime:
    return datetime.combine(value, time(hour=12), timezone).astimezone(UTC)


def matches(
    event: CalendarEvent,
    *,
    source_type: str | None,
    event_status: str | None,
    user_id: str | None,
    scope: str | None,
) -> bool:
    return not (
        (source_type and event.source_type != source_type)
        or (event_status and event.status != event_status)
        or (user_id and user_id not in event.user_ids)
        or (scope and event.scope != scope)
    )


@router.get("", response_model=list[CalendarEvent])
async def calendar_events(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    start: datetime,
    end: datetime,
    source_type: str | None = Query(default=None, alias="type"),
    event_status: str | None = Query(default=None, alias="status"),
    user_id: str | None = None,
    scope: str | None = Query(default=None, pattern="^(personal|shared)$"),
) -> list[CalendarEvent]:
    start_utc, end_utc = aware(start), aware(end)
    if end_utc <= start_utc:
        raise HTTPException(status_code=422, detail="Конец периода должен быть позже начала")
    house = await db.scalar(select(Household).where(Household.id == auth.user.household_id))
    if house is None:
        raise HTTPException(status_code=404, detail="Семья не найдена")
    timezone = ZoneInfo(house.timezone)
    start_date = start_utc.astimezone(timezone).date()
    end_date = end_utc.astimezone(timezone).date()
    events: list[CalendarEvent] = []

    instances = list(
        await db.scalars(
            select(TaskInstance)
            .join(TaskDefinition)
            .where(
                TaskDefinition.household_id == house.id,
                TaskInstance.due_at >= start_utc,
                TaskInstance.due_at < end_utc,
            )
        )
    )
    for instance in instances:
        task = await db.scalar(select(TaskDefinition).where(TaskDefinition.id == instance.task_id))
        if task is None or instance.due_at is None:
            continue
        assigned = list(
            await db.scalars(
                select(TaskAssignment.user_id).where(TaskAssignment.task_id == task.id)
            )
        )
        ids = list(
            dict.fromkeys(([instance.assignee_id] if instance.assignee_id else []) + assigned)
        )
        events.append(
            CalendarEvent(
                id=f"task:{instance.id}",
                source_type="task",
                source_id=instance.id,
                title=task.title,
                starts_at=utc_value(instance.due_at),
                status=instance.status,
                user_ids=ids,
                scope="personal" if ids else "shared",
                editable=auth.user.role != UserRole.CHILD,
                recurring=bool(task.repeat_rule.get("kind") not in (None, "none")),
            )
        )

    shopping = list(
        await db.scalars(
            select(ShoppingList).where(
                ShoppingList.household_id == house.id,
                ShoppingList.scheduled_at >= start_utc,
                ShoppingList.scheduled_at < end_utc,
            )
        )
    )
    events += [
        CalendarEvent(
            id=f"shopping:{item.id}",
            source_type="shopping",
            source_id=item.id,
            title=item.title,
            starts_at=utc_value(item.scheduled_at),
            status=item.status,
            user_ids=[item.responsible_id] if item.responsible_id else [],
            scope="personal" if item.responsible_id else "shared",
            editable=auth.user.role != UserRole.CHILD,
        )
        for item in shopping
        if item.scheduled_at is not None
    ]
    plans = list(
        await db.scalars(
            select(MaintenancePlan).where(
                MaintenancePlan.household_id == house.id,
                MaintenancePlan.next_on >= start_date,
                MaintenancePlan.next_on <= end_date,
                MaintenancePlan.is_active.is_(True),
            )
        )
    )
    events += [
        CalendarEvent(
            id=f"maintenance:{item.id}",
            source_type="maintenance",
            source_id=item.id,
            title=item.title,
            starts_at=date_at_noon(item.next_on, timezone),
            status="overdue" if item.next_on < datetime.now(timezone).date() else "planned",
            user_ids=[item.responsible_id] if item.responsible_id else [],
            scope="personal" if item.responsible_id else "shared",
            editable=auth.user.role != UserRole.CHILD,
            recurring=True,
        )
        for item in plans
    ]
    if house.meters_enabled and house.module_settings.get("meters", True):
        meters = list(
            await db.scalars(
                select(Meter).where(
                    Meter.household_id == house.id,
                    Meter.next_submission_on >= start_date,
                    Meter.next_submission_on <= end_date,
                    Meter.is_active.is_(True),
                )
            )
        )
        events += [
            CalendarEvent(
                id=f"meter:{item.id}",
                source_type="meter",
                source_id=item.id,
                title=f"Показания: {item.meter_type}",
                starts_at=date_at_noon(item.next_submission_on, timezone),
                status="planned",
                user_ids=[item.responsible_id] if item.responsible_id else [],
                scope="personal" if item.responsible_id else "shared",
                editable=auth.user.role != UserRole.CHILD,
                recurring=True,
            )
            for item in meters
            if item.next_submission_on is not None
        ]
    equipment = list(
        await db.scalars(
            select(Equipment).where(
                Equipment.household_id == house.id,
                Equipment.warranty_until >= start_date,
                Equipment.warranty_until <= end_date,
                Equipment.archived_at.is_(None),
            )
        )
    )
    events += [
        CalendarEvent(
            id=f"warranty:{item.id}",
            source_type="warranty",
            source_id=item.id,
            title=f"Гарантия: {item.name or 'оборудование'}",
            starts_at=date_at_noon(item.warranty_until, timezone),
            status="planned",
            user_ids=[item.responsible_id] if item.responsible_id else [],
            scope="personal" if item.responsible_id else "shared",
            editable=auth.user.role != UserRole.CHILD,
        )
        for item in equipment
        if item.warranty_until is not None
    ]
    storage = list(
        await db.scalars(
            select(StorageItem).where(
                StorageItem.household_id == house.id,
                StorageItem.review_at >= start_utc,
                StorageItem.review_at < end_utc,
                StorageItem.archived_at.is_(None),
            )
        )
    )
    events += [
        CalendarEvent(
            id=f"storage:{item.id}",
            source_type="storage",
            source_id=item.id,
            title=f"Пересмотреть хранение: {item.name}",
            starts_at=utc_value(item.review_at),
            status=item.review_status,
            user_ids=[item.owner_id] if item.owner_id else [],
            scope="personal" if item.owner_id else "shared",
            editable=auth.user.role != UserRole.CHILD,
        )
        for item in storage
        if item.review_at is not None
    ]
    return sorted(
        [
            item
            for item in events
            if matches(
                item,
                source_type=source_type,
                event_status=event_status,
                user_id=user_id,
                scope=scope,
            )
        ],
        key=lambda item: item.starts_at,
    )


@router.post("/move", response_model=Message)
async def move_calendar_event(
    payload: CalendarMove,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(status_code=403, detail="Переносить события может взрослый")
    starts_at = aware(payload.starts_at)
    local_date = starts_at.date()
    household_id = auth.user.household_id
    if payload.source_type == "task":
        instance = await db.scalar(
            select(TaskInstance)
            .join(TaskDefinition)
            .where(
                TaskInstance.id == payload.source_id,
                TaskDefinition.household_id == household_id,
            )
        )
        if instance is None:
            raise HTTPException(status_code=404, detail="Дело не найдено")
        if payload.recurrence_scope == "series" and instance.due_at:
            current_due = instance.due_at
            if current_due.tzinfo is None:
                current_due = current_due.replace(tzinfo=UTC)
            delta = starts_at - current_due
            series = await db.scalars(
                select(TaskInstance).where(
                    TaskInstance.task_id == instance.task_id,
                    TaskInstance.status != "completed",
                    TaskInstance.due_at.is_not(None),
                )
            )
            for item in series:
                if item.due_at:
                    current = item.due_at
                    if current.tzinfo is None:
                        current = current.replace(tzinfo=UTC)
                    item.due_at = current + delta
        else:
            instance.due_at = starts_at
    elif payload.source_type == "shopping":
        item = await db.scalar(
            select(ShoppingList).where(
                ShoppingList.id == payload.source_id,
                ShoppingList.household_id == household_id,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Список не найден")
        item.scheduled_at = starts_at
        item.status = "planned"
    elif payload.source_type == "maintenance":
        item = await db.scalar(
            select(MaintenancePlan).where(
                MaintenancePlan.id == payload.source_id,
                MaintenancePlan.household_id == household_id,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Регламент не найден")
        item.next_on = local_date
    elif payload.source_type == "meter":
        item = await db.scalar(
            select(Meter).where(Meter.id == payload.source_id, Meter.household_id == household_id)
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Счётчик не найден")
        item.next_submission_on = local_date
    elif payload.source_type == "warranty":
        item = await db.scalar(
            select(Equipment).where(
                Equipment.id == payload.source_id, Equipment.household_id == household_id
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Оборудование не найдено")
        item.warranty_until = local_date
    else:
        item = await db.scalar(
            select(StorageItem).where(
                StorageItem.id == payload.source_id, StorageItem.household_id == household_id
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Вещь не найдена")
        item.review_at = starts_at
        item.review_status = "active"
    await db.commit()
    return Message(message="Дата перенесена")
