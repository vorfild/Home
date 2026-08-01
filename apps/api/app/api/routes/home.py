from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.db.session import get_db_session
from app.models.home import Equipment, MaintenancePlan, MaintenanceRecord, Meter, MeterReading
from app.models.identity import Household, User, UserRole
from app.models.storage import StorageItem, StorageNode
from app.models.tasks import TaskDefinition, TaskInstance
from app.schemas.home import (
    EquipmentCreate,
    EquipmentRead,
    EquipmentUpdate,
    HomeOverview,
    MaintenanceComplete,
    MaintenanceCreate,
    MaintenanceRead,
    MeterCreate,
    MeterRead,
    MeterReplace,
    ModuleToggle,
    ReadingCreate,
    ReadingRead,
    RepairCreate,
    RepairRead,
)
from app.services.auth import now_utc
from app.services.home import record_completed_maintenance

router = APIRouter(prefix="/home", tags=["home"])


def ensure_adult(auth: AuthContext) -> None:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Раздел изменяет взрослый"
        )


def ensure_admin(auth: AuthContext) -> None:
    if auth.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нужны права администратора"
        )


async def validate_responsible(db: AsyncSession, household_id: str, user_id: str | None) -> None:
    if user_id is None:
        return
    exists = await db.scalar(
        select(User.id).where(
            User.id == user_id, User.household_id == household_id, User.is_active.is_(True)
        )
    )
    if exists is None:
        raise HTTPException(status_code=400, detail="Ответственный не найден")


async def household(db: AsyncSession, household_id: str) -> Household:
    item = await db.scalar(select(Household).where(Household.id == household_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Семья не найдена")
    return item


async def read_equipment(db: AsyncSession, item: Equipment) -> EquipmentRead:
    values: dict[str, object] = {
        "id": item.id,
        "storage_item_id": item.storage_item_id,
        "name": item.name or "Оборудование",
        "photo_ids": item.photo_ids,
        "category": item.category,
        "location": item.location,
        "manufacturer": item.manufacturer,
        "model": item.model,
        "serial_number": item.serial_number,
        "acquired_on": item.acquired_on,
        "warranty_until": item.warranty_until,
        "document_ids": item.document_ids,
        "condition": item.condition,
        "responsible_id": item.responsible_id,
    }
    if item.storage_item_id:
        stored = await db.scalar(
            select(StorageItem).where(
                StorageItem.id == item.storage_item_id,
                StorageItem.household_id == item.household_id,
                StorageItem.archived_at.is_(None),
            )
        )
        if stored is not None:
            node_name = await db.scalar(
                select(StorageNode.name).where(StorageNode.id == stored.node_id)
            )
            values.update(
                name=stored.name,
                photo_ids=stored.photo_ids,
                category=stored.category,
                location=node_name,
                manufacturer=stored.manufacturer,
                model=stored.model,
                serial_number=stored.serial_number,
                acquired_on=stored.purchased_on,
                warranty_until=stored.warranty_until,
            )
    return EquipmentRead.model_validate(values)


async def load_equipment(db: AsyncSession, equipment_id: str, household_id: str) -> Equipment:
    item = await db.scalar(
        select(Equipment).where(
            Equipment.id == equipment_id,
            Equipment.household_id == household_id,
            Equipment.archived_at.is_(None),
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Оборудование не найдено")
    return item


@router.get("/equipment", response_model=list[EquipmentRead])
async def list_equipment(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[EquipmentRead]:
    items = list(
        await db.scalars(
            select(Equipment).where(
                Equipment.household_id == auth.user.household_id,
                Equipment.archived_at.is_(None),
            )
        )
    )
    return [await read_equipment(db, item) for item in items]


@router.post("/equipment", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    payload: EquipmentCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> EquipmentRead:
    ensure_adult(auth)
    await validate_responsible(db, auth.user.household_id, payload.responsible_id)
    linked = None
    if payload.storage_item_id:
        linked = await db.scalar(
            select(StorageItem).where(
                StorageItem.id == payload.storage_item_id,
                StorageItem.household_id == auth.user.household_id,
                StorageItem.archived_at.is_(None),
            )
        )
        if linked is None:
            raise HTTPException(status_code=400, detail="Карточка кладовой не найдена")
        if await db.scalar(select(Equipment.id).where(Equipment.storage_item_id == linked.id)):
            raise HTTPException(status_code=409, detail="Карточка уже связана с оборудованием")
    data = payload.model_dump()
    if linked is not None:
        for key in (
            "name",
            "photo_ids",
            "category",
            "location",
            "manufacturer",
            "model",
            "serial_number",
            "acquired_on",
            "warranty_until",
        ):
            data[key] = [] if key == "photo_ids" else None
    item = Equipment(household_id=auth.user.household_id, **data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return await read_equipment(db, item)


@router.patch("/equipment/{equipment_id}", response_model=EquipmentRead)
async def update_equipment(
    equipment_id: str,
    payload: EquipmentUpdate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> EquipmentRead:
    ensure_adult(auth)
    item = await load_equipment(db, equipment_id, auth.user.household_id)
    changes = payload.model_dump(exclude_unset=True)
    await validate_responsible(db, auth.user.household_id, changes.get("responsible_id"))
    if item.storage_item_id:
        changes = {
            key: value
            for key, value in changes.items()
            if key in {"condition", "responsible_id", "document_ids"}
        }
    for key, value in changes.items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return await read_equipment(db, item)


@router.get("/maintenance", response_model=list[MaintenanceRead])
async def list_maintenance(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MaintenancePlan]:
    return list(
        await db.scalars(
            select(MaintenancePlan)
            .where(MaintenancePlan.household_id == auth.user.household_id)
            .order_by(MaintenancePlan.next_on)
        )
    )


@router.post("/maintenance", response_model=MaintenanceRead, status_code=status.HTTP_201_CREATED)
async def create_maintenance(
    payload: MaintenanceCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaintenancePlan:
    ensure_adult(auth)
    await validate_responsible(db, auth.user.household_id, payload.responsible_id)
    if payload.equipment_id:
        await load_equipment(db, payload.equipment_id, auth.user.household_id)
    item = MaintenancePlan(household_id=auth.user.household_id, **payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def load_plan(db: AsyncSession, plan_id: str, household_id: str) -> MaintenancePlan:
    item = await db.scalar(
        select(MaintenancePlan).where(
            MaintenancePlan.id == plan_id, MaintenancePlan.household_id == household_id
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Регламент не найден")
    return item


@router.post("/maintenance/{plan_id}/complete", response_model=RepairRead)
async def complete_maintenance(
    plan_id: str,
    payload: MaintenanceComplete,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaintenanceRecord:
    ensure_adult(auth)
    plan = await load_plan(db, plan_id, auth.user.household_id)
    if plan.requires_photo and not payload.photo_ids:
        raise HTTPException(status_code=422, detail="Нужно фото")
    if plan.open_task_id:
        instance = await db.scalar(select(TaskInstance).where(TaskInstance.id == plan.open_task_id))
        if instance is not None and instance.status != "completed":
            instance.status = "completed"
            instance.completed_at = datetime.combine(payload.performed_on, time(hour=12), UTC)
            instance.completed_by_id = auth.user.id
            instance.completion_comment = payload.comment
            instance.completion_cost = payload.actual_cost
            instance.completion_photo_ids = payload.photo_ids
            task = await db.scalar(
                select(TaskDefinition).where(TaskDefinition.id == instance.task_id)
            )
            if task is not None:
                record = await record_completed_maintenance(
                    db, task, instance, instance.completed_at
                )
                if record is not None:
                    await db.commit()
                    await db.refresh(record)
                    return record
    performed = payload.performed_on
    record = MaintenanceRecord(
        household_id=auth.user.household_id,
        equipment_id=plan.equipment_id,
        plan_id=plan.id,
        record_type="maintenance",
        title=plan.title,
        performed_on=performed,
        comment=payload.comment,
        actual_cost=payload.actual_cost,
        photo_ids=payload.photo_ids,
        keep_forever=False,
        purge_after=datetime.combine(performed + timedelta(days=730), time.min, UTC),
    )
    db.add(record)
    plan.previous_on = performed
    plan.next_on = performed + timedelta(days=plan.interval_days)
    plan.open_task_id = None
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/repairs", response_model=list[RepairRead])
async def list_repairs(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    record_type: str = Query(default="all", pattern="^(all|repair|maintenance)$"),
) -> list[MaintenanceRecord]:
    query = select(MaintenanceRecord).where(
        MaintenanceRecord.household_id == auth.user.household_id
    )
    if record_type != "all":
        query = query.where(MaintenanceRecord.record_type == record_type)
    return list(await db.scalars(query.order_by(MaintenanceRecord.performed_on.desc())))


@router.post("/repairs", response_model=RepairRead, status_code=status.HTTP_201_CREATED)
async def create_repair(
    payload: RepairCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaintenanceRecord:
    ensure_adult(auth)
    if payload.equipment_id:
        await load_equipment(db, payload.equipment_id, auth.user.household_id)
    purge_after = None
    if not payload.keep_forever:
        purge_after = datetime.combine(payload.performed_on + timedelta(days=730), time.min, UTC)
    item = MaintenanceRecord(
        household_id=auth.user.household_id,
        record_type="repair",
        purge_after=purge_after,
        **payload.model_dump(),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def ensure_meters_enabled(db: AsyncSession, household_id: str) -> None:
    if not (await household(db, household_id)).meters_enabled:
        raise HTTPException(status_code=409, detail="Модуль счётчиков выключен")


@router.put("/meters/module")
async def toggle_meters(
    payload: ModuleToggle,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, bool]:
    ensure_admin(auth)
    item = await household(db, auth.user.household_id)
    item.meters_enabled = payload.enabled
    item.module_settings = {**item.module_settings, "meters": payload.enabled}
    await db.commit()
    return {"enabled": item.meters_enabled}


@router.get("/meters", response_model=list[MeterRead])
async def list_meters(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[Meter]:
    await ensure_meters_enabled(db, auth.user.household_id)
    return list(
        await db.scalars(
            select(Meter)
            .where(Meter.household_id == auth.user.household_id, Meter.is_active.is_(True))
            .order_by(Meter.meter_type)
        )
    )


@router.post("/meters", response_model=MeterRead, status_code=status.HTTP_201_CREATED)
async def create_meter(
    payload: MeterCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Meter:
    ensure_adult(auth)
    await ensure_meters_enabled(db, auth.user.household_id)
    await validate_responsible(db, auth.user.household_id, payload.responsible_id)
    item = Meter(household_id=auth.user.household_id, **payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def load_meter(db: AsyncSession, meter_id: str, household_id: str) -> Meter:
    item = await db.scalar(
        select(Meter).where(Meter.id == meter_id, Meter.household_id == household_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Счётчик не найден")
    return item


@router.get("/meters/{meter_id}/readings", response_model=list[ReadingRead])
async def list_readings(
    meter_id: str,
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[MeterReading]:
    await ensure_meters_enabled(db, auth.user.household_id)
    meter = await load_meter(db, meter_id, auth.user.household_id)
    return list(
        await db.scalars(
            select(MeterReading)
            .where(MeterReading.meter_id == meter.id)
            .order_by(MeterReading.read_on, MeterReading.created_at)
        )
    )


@router.post("/meters/{meter_id}/readings", response_model=ReadingRead, status_code=201)
async def add_reading(
    meter_id: str,
    payload: ReadingCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MeterReading:
    ensure_adult(auth)
    await ensure_meters_enabled(db, auth.user.household_id)
    meter = await load_meter(db, meter_id, auth.user.household_id)
    previous = meter.last_value
    decreased = previous is not None and payload.value < previous
    if decreased and not payload.accept_decrease:
        raise HTTPException(
            status_code=409,
            detail="Новое показание меньше предыдущего; подтвердите ввод или выполните замену",
        )
    reading = MeterReading(
        meter_id=meter.id,
        value=payload.value,
        read_on=payload.read_on,
        photo_id=payload.photo_id,
        comment=payload.comment,
        consumption=payload.value - previous if previous is not None and not decreased else None,
        decrease_warning=decreased,
        reset_sequence=meter.reset_sequence,
    )
    db.add(reading)
    meter.last_value = payload.value
    meter.next_submission_on = payload.next_submission_on
    if meter.open_task_id:
        task = await db.scalar(select(TaskInstance).where(TaskInstance.id == meter.open_task_id))
        if task is not None and task.status != "completed":
            task.status = "completed"
            task.completed_at = now_utc()
            task.completed_by_id = auth.user.id
        meter.open_task_id = None
    await db.commit()
    await db.refresh(reading)
    return reading


@router.post("/meters/{meter_id}/replace", response_model=ReadingRead)
async def replace_meter(
    meter_id: str,
    payload: MeterReplace,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> MeterReading:
    ensure_adult(auth)
    await ensure_meters_enabled(db, auth.user.household_id)
    meter = await load_meter(db, meter_id, auth.user.household_id)
    meter.reset_sequence += 1
    meter.serial_number = payload.serial_number
    meter.last_value = payload.start_value
    reading = MeterReading(
        meter_id=meter.id,
        value=payload.start_value,
        read_on=payload.replaced_on,
        comment=payload.comment or "Замена или сброс счётчика",
        consumption=None,
        decrease_warning=False,
        reset_sequence=meter.reset_sequence,
    )
    db.add(reading)
    await db.commit()
    await db.refresh(reading)
    return reading


@router.get("/overview", response_model=HomeOverview)
async def overview(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> HomeOverview:
    today = date.today()
    end = today + timedelta(days=45)
    plans = list(
        await db.scalars(
            select(MaintenancePlan)
            .where(
                MaintenancePlan.household_id == auth.user.household_id,
                MaintenancePlan.is_active.is_(True),
                MaintenancePlan.next_on <= end,
            )
            .order_by(MaintenancePlan.next_on)
        )
    )
    equipment = list(
        await db.scalars(
            select(Equipment).where(
                Equipment.household_id == auth.user.household_id,
                Equipment.archived_at.is_(None),
            )
        )
    )
    house = await household(db, auth.user.household_id)
    meters: list[Meter] = []
    if house.meters_enabled:
        meters = list(
            await db.scalars(
                select(Meter).where(
                    Meter.household_id == auth.user.household_id,
                    Meter.next_submission_on <= end,
                    Meter.is_active.is_(True),
                )
            )
        )
    warranties = [item for item in equipment if item.warranty_until and item.warranty_until <= end]
    attention = [item for item in equipment if item.condition != "working"]
    return HomeOverview(
        meters_enabled=house.meters_enabled,
        maintenance_due=[MaintenanceRead.model_validate(item) for item in plans],
        warranties_expiring=[await read_equipment(db, item) for item in warranties],
        meter_deadlines=[MeterRead.model_validate(item) for item in meters],
        equipment_attention=[await read_equipment(db, item) for item in attention],
    )
