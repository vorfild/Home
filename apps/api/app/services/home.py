from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.home import MaintenancePlan, MaintenanceRecord, Meter
from app.models.identity import Household
from app.models.tasks import TaskAssignment, TaskDefinition, TaskInstance, TaskSubtask


def utc_due(on_date: date) -> datetime:
    return datetime.combine(on_date, time(hour=9), UTC)


async def _definition_for_plan(db: AsyncSession, plan: MaintenancePlan) -> TaskDefinition:
    task = await db.scalar(
        select(TaskDefinition).where(
            TaskDefinition.source_type == "maintenance", TaskDefinition.source_id == plan.id
        )
    )
    if task is not None:
        task.is_active = True
        return task
    task = TaskDefinition(
        household_id=plan.household_id,
        title=plan.title,
        description="Плановое обслуживание оборудования",
        category="обслуживание",
        priority="high",
        assignment_mode="fixed" if plan.responsible_id else "anyone",
        repeat_rule={},
        reminders=[],
        requires_photo=plan.requires_photo,
        requires_adult_review=False,
        source_type="maintenance",
        source_id=plan.id,
    )
    task.subtasks = [
        TaskSubtask(title=item, position=index) for index, item in enumerate(plan.checklist)
    ]
    if plan.responsible_id:
        task.assignments = [TaskAssignment(user_id=plan.responsible_id, position=0)]
    db.add(task)
    await db.flush()
    return task


async def process_maintenance_schedules(db: AsyncSession, *, today: date | None = None) -> int:
    current = today or datetime.now(UTC).date()
    plans = list(
        await db.scalars(
            select(MaintenancePlan).where(
                MaintenancePlan.is_active.is_(True),
                MaintenancePlan.next_on <= current,
                MaintenancePlan.open_task_id.is_(None),
            )
        )
    )
    created = 0
    for plan in plans:
        task = await _definition_for_plan(db, plan)
        sequence = (
            int(
                await db.scalar(
                    select(func.coalesce(func.max(TaskInstance.sequence), 0)).where(
                        TaskInstance.task_id == task.id
                    )
                )
                or 0
            )
            + 1
        )
        instance = TaskInstance(
            task_id=task.id,
            sequence=sequence,
            due_at=utc_due(plan.next_on),
            assignee_id=plan.responsible_id,
            status="open",
            subtask_state={item.id: False for item in task.subtasks},
        )
        db.add(instance)
        await db.flush()
        plan.open_task_id = instance.id
        created += 1
    return created


async def record_completed_maintenance(
    db: AsyncSession,
    task: TaskDefinition,
    instance: TaskInstance,
    completed_at: datetime,
) -> MaintenanceRecord | None:
    if task.source_type != "maintenance" or not task.source_id:
        return None
    existing = await db.scalar(
        select(MaintenanceRecord).where(MaintenanceRecord.task_instance_id == instance.id)
    )
    if existing is not None:
        return existing
    plan = await db.scalar(select(MaintenancePlan).where(MaintenancePlan.id == task.source_id))
    if plan is None:
        return None
    performed_on = completed_at.date()
    record = MaintenanceRecord(
        household_id=plan.household_id,
        equipment_id=plan.equipment_id,
        plan_id=plan.id,
        task_instance_id=instance.id,
        record_type="maintenance",
        title=plan.title,
        performed_on=performed_on,
        comment=instance.completion_comment,
        actual_cost=Decimal(str(instance.completion_cost))
        if instance.completion_cost is not None
        else None,
        photo_ids=instance.completion_photo_ids,
        keep_forever=False,
        purge_after=datetime.combine(performed_on + timedelta(days=730), time.min, UTC),
    )
    db.add(record)
    plan.previous_on = performed_on
    plan.next_on = performed_on + timedelta(days=plan.interval_days)
    plan.open_task_id = None
    return record


async def _definition_for_meter(db: AsyncSession, meter: Meter) -> TaskDefinition:
    task = await db.scalar(
        select(TaskDefinition).where(
            TaskDefinition.source_type == "meter_submission", TaskDefinition.source_id == meter.id
        )
    )
    if task is not None:
        task.is_active = True
        return task
    task = TaskDefinition(
        household_id=meter.household_id,
        title=f"Передать показания: {meter.meter_type}",
        category="счётчики",
        priority="normal",
        assignment_mode="fixed" if meter.responsible_id else "anyone",
        repeat_rule={},
        reminders=[],
        requires_photo=False,
        requires_adult_review=False,
        source_type="meter_submission",
        source_id=meter.id,
    )
    if meter.responsible_id:
        task.assignments = [TaskAssignment(user_id=meter.responsible_id, position=0)]
    db.add(task)
    await db.flush()
    return task


async def process_meter_schedules(db: AsyncSession, *, today: date | None = None) -> int:
    current = today or datetime.now(UTC).date()
    meters = list(
        await db.scalars(
            select(Meter)
            .join(Household, Household.id == Meter.household_id)
            .where(
                Household.meters_enabled.is_(True),
                Meter.is_active.is_(True),
                Meter.next_submission_on <= current,
                Meter.open_task_id.is_(None),
            )
        )
    )
    created = 0
    for meter in meters:
        task = await _definition_for_meter(db, meter)
        sequence = (
            int(
                await db.scalar(
                    select(func.coalesce(func.max(TaskInstance.sequence), 0)).where(
                        TaskInstance.task_id == task.id
                    )
                )
                or 0
            )
            + 1
        )
        instance = TaskInstance(
            task_id=task.id,
            sequence=sequence,
            due_at=utc_due(meter.next_submission_on or current),
            assignee_id=meter.responsible_id,
            status="open",
            subtask_state={},
        )
        db.add(instance)
        await db.flush()
        meter.open_task_id = instance.id
        created += 1
    return created


async def purge_expired_repair_history(db: AsyncSession, *, now: datetime | None = None) -> int:
    moment = now or datetime.now(UTC)
    ids = list(
        await db.scalars(
            select(MaintenanceRecord.id).where(
                MaintenanceRecord.keep_forever.is_(False),
                MaintenanceRecord.purge_after.is_not(None),
                MaintenanceRecord.purge_after <= moment,
            )
        )
    )
    if not ids:
        return 0
    await db.execute(
        delete(MaintenanceRecord).where(
            MaintenanceRecord.id.in_(ids),
            MaintenanceRecord.keep_forever.is_(False),
        )
    )
    return len(ids)


async def process_home_schedules(db: AsyncSession) -> int:
    return (
        await process_maintenance_schedules(db)
        + await process_meter_schedules(db)
        + await purge_expired_repair_history(db)
    )
