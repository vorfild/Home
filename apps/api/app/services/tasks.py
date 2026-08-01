from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Absence, User
from app.models.tasks import TaskDefinition, TaskInstance, TaskQueueMember


def add_months(value: datetime, months: int) -> datetime:
    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def add_years(value: datetime, years: int) -> datetime:
    year = value.year + years
    day = min(value.day, calendar.monthrange(year, value.month)[1])
    return value.replace(year=year, day=day)


def next_due_at(
    previous: datetime | None, completed_at: datetime, rule: dict[str, Any]
) -> datetime | None:
    kind = str(rule.get("kind", "none"))
    if kind == "none" or previous is None:
        return None
    interval = max(1, int(rule.get("interval", 1)))
    anchor = completed_at if kind == "after_completion" else previous
    if kind == "daily":
        return previous + timedelta(days=1)
    if kind == "weekly":
        return previous + timedelta(weeks=1)
    if kind == "monthly":
        return add_months(previous, 1)
    if kind == "yearly":
        return add_years(previous, 1)
    if kind in {"interval", "after_completion"}:
        unit = str(rule.get("unit", "days"))
        if unit == "weeks":
            return anchor + timedelta(weeks=interval)
        if unit == "months":
            return add_months(anchor, interval)
        if unit == "years":
            return add_years(anchor, interval)
        return anchor + timedelta(days=interval)
    if kind == "weekdays":
        weekdays = [int(item) for item in rule.get("weekdays", [])]
        if not weekdays:
            return None
        candidate = previous
        for _ in range(8):
            candidate += timedelta(days=1)
            if candidate.weekday() in weekdays:
                return candidate
    if kind == "day_of_month":
        desired = int(rule.get("day_of_month", previous.day))
        target = add_months(previous, 1)
        return target.replace(day=min(desired, calendar.monthrange(target.year, target.month)[1]))
    if kind == "seasonal":
        months = sorted({int(item) for item in rule.get("months", [])})
        for offset in range(1, 25):
            target = add_months(previous, offset)
            if target.month in months:
                return target
    return None


async def user_is_absent(db: AsyncSession, user_id: str, on_date: date) -> Absence | None:
    return await db.scalar(
        select(Absence).where(
            Absence.user_id == user_id,
            Absence.starts_on <= on_date,
            Absence.ends_on >= on_date,
        )
    )


async def queue_assignee(
    db: AsyncSession, task: TaskDefinition, *, on_date: date
) -> tuple[str | None, int]:
    members = list(
        await db.scalars(
            select(TaskQueueMember)
            .join(User, User.id == TaskQueueMember.user_id)
            .where(TaskQueueMember.task_id == task.id, User.is_active.is_(True))
            .order_by(TaskQueueMember.position)
        )
    )
    if not members:
        return None, 0
    start = task.current_queue_index % len(members)
    for offset in range(len(members)):
        index = (start + offset) % len(members)
        absence = await user_is_absent(db, members[index].user_id, on_date)
        if absence is None:
            return members[index].user_id, index
        if absence.substitute_user_id:
            substitute = await db.scalar(
                select(User).where(User.id == absence.substitute_user_id, User.is_active.is_(True))
            )
            if substitute:
                return substitute.id, index
    return None, start


async def build_next_instance(
    db: AsyncSession, task: TaskDefinition, completed: TaskInstance, completed_at: datetime
) -> TaskInstance | None:
    due_at = next_due_at(completed.due_at, completed_at, task.repeat_rule)
    if due_at is None:
        return None
    existing = await db.scalar(
        select(TaskInstance.id).where(
            TaskInstance.task_id == task.id,
            TaskInstance.status.in_(["open", "awaiting_review", "rejected"]),
        )
    )
    if existing is not None:
        return None
    assignee_id: str | None = None
    if task.assignment_mode == "queue":
        assignee_id, index = await queue_assignee(db, task, on_date=due_at.date())
        task.current_queue_index = index
    instance = TaskInstance(
        task_id=task.id,
        sequence=completed.sequence + 1,
        due_at=due_at.astimezone(UTC) if due_at.tzinfo else due_at.replace(tzinfo=UTC),
        assignee_id=assignee_id,
        status="open",
        subtask_state={subtask.id: False for subtask in task.subtasks},
    )
    db.add(instance)
    return instance
