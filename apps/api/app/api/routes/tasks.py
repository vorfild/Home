from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies.auth import AuthContext, csrf_auth, current_auth
from app.db.session import get_db_session
from app.models.identity import Household, User, UserRole
from app.models.tasks import (
    TaskAssignment,
    TaskDefinition,
    TaskHistory,
    TaskInstance,
    TaskQueueMember,
    TaskSubtask,
)
from app.schemas.common import Message
from app.schemas.tasks import TaskComplete, TaskCreate, TaskHistoryRead, TaskRead, TaskReview
from app.services.auth import now_utc
from app.services.tasks import build_next_instance, queue_assignee

router = APIRouter(prefix="/tasks", tags=["tasks"])


def ensure_adult(auth: AuthContext) -> None:
    if auth.user.role == UserRole.CHILD:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Дело создаёт взрослый")


def task_options() -> tuple[Any, ...]:
    return (
        selectinload(TaskDefinition.assignments),
        selectinload(TaskDefinition.queue),
        selectinload(TaskDefinition.subtasks),
    )


async def household_timezone(db: AsyncSession, household_id: str) -> ZoneInfo:
    name = await db.scalar(select(Household.timezone).where(Household.id == household_id))
    return ZoneInfo(name or "Europe/Moscow")


async def load_instance(db: AsyncSession, instance_id: str, household_id: str) -> TaskInstance:
    instance = await db.scalar(
        select(TaskInstance)
        .join(TaskDefinition)
        .options(selectinload(TaskInstance.task).options(*task_options()))
        .where(TaskInstance.id == instance_id, TaskDefinition.household_id == household_id)
    )
    if instance is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Дело не найдено")
    return instance


def read_task(instance: TaskInstance) -> TaskRead:
    task = instance.task
    queue_ids = [member.user_id for member in task.queue]
    next_queue: str | None = None
    if queue_ids:
        next_queue = queue_ids[(task.current_queue_index + 1) % len(queue_ids)]
    return TaskRead(
        id=instance.id,
        definition_id=task.id,
        title=task.title,
        description=task.description,
        room=task.room,
        category=task.category,
        due_at=instance.due_at,
        estimated_minutes=task.estimated_minutes,
        priority=task.priority,
        assignment_mode=task.assignment_mode,
        assignee_ids=[assignment.user_id for assignment in task.assignments],
        queue_user_ids=queue_ids,
        current_queue_user_id=instance.assignee_id,
        next_queue_user_id=next_queue,
        subtasks=[
            {
                "id": item.id,
                "title": item.title,
                "completed": bool(instance.subtask_state.get(item.id, False)),
            }
            for item in task.subtasks
        ],
        repeat=task.repeat_rule,
        requires_photo=task.requires_photo,
        requires_adult_review=task.requires_adult_review,
        status=instance.status,
        completed_by_id=instance.completed_by_id,
        completed_at=instance.completed_at,
        review_comment=instance.review_comment,
        source_type=task.source_type,
    )


async def validate_users(db: AsyncSession, household_id: str, user_ids: list[str]) -> None:
    if not user_ids:
        return
    found = set(
        await db.scalars(
            select(User.id).where(
                User.household_id == household_id,
                User.id.in_(user_ids),
                User.is_active.is_(True),
            )
        )
    )
    if found != set(user_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ответственный должен быть активным членом семьи",
        )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskRead:
    ensure_adult(auth)
    await validate_users(db, auth.user.household_id, payload.assignee_ids + payload.queue_user_ids)
    due_at = payload.due_at
    if due_at and due_at.tzinfo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Дата дела должна содержать часовой пояс",
        )
    task = TaskDefinition(
        household_id=auth.user.household_id,
        title=payload.title.strip(),
        description=payload.description.strip() if payload.description else None,
        room=payload.room.strip() if payload.room else None,
        category=payload.category.strip(),
        estimated_minutes=payload.estimated_minutes,
        priority=payload.priority,
        assignment_mode=payload.assignment_mode,
        repeat_rule=payload.repeat.model_dump(mode="json"),
        reminders=payload.reminders,
        requires_photo=payload.requires_photo,
        requires_adult_review=payload.requires_adult_review,
    )
    task.assignments = [
        TaskAssignment(user_id=user_id, position=index)
        for index, user_id in enumerate(payload.assignee_ids)
    ]
    task.queue = [
        TaskQueueMember(user_id=user_id, position=index)
        for index, user_id in enumerate(payload.queue_user_ids)
    ]
    task.subtasks = [
        TaskSubtask(title=title.strip(), position=index)
        for index, title in enumerate(payload.subtasks)
        if title.strip()
    ]
    db.add(task)
    await db.flush()
    assignee_id = payload.assignee_ids[0] if payload.assignment_mode == "fixed" else None
    if payload.assignment_mode == "queue":
        local_date = (due_at or now_utc()).date()
        assignee_id, task.current_queue_index = await queue_assignee(db, task, on_date=local_date)
    instance = TaskInstance(
        task_id=task.id,
        sequence=1,
        due_at=due_at.astimezone(UTC) if due_at else None,
        assignee_id=assignee_id,
        status="open",
        subtask_state={item.id: False for item in task.subtasks},
    )
    db.add(instance)
    db.add(
        TaskHistory(
            task_id=task.id,
            actor_id=auth.user.id,
            action="created",
            happened_at=now_utc(),
        )
    )
    await db.commit()
    loaded = await load_instance(db, instance.id, auth.user.household_id)
    return read_task(loaded)


@router.get("", response_model=list[TaskRead])
async def list_tasks(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    view: str = Query(default="active", pattern="^(active|completed|recurring)$"),
    user_id: str | None = None,
    category: str | None = None,
    room: str | None = None,
    task_status: str | None = Query(default=None, alias="status"),
) -> list[TaskRead]:
    query = (
        select(TaskInstance)
        .join(TaskDefinition)
        .options(selectinload(TaskInstance.task).options(*task_options()))
        .where(TaskDefinition.household_id == auth.user.household_id)
    )
    if view == "completed":
        query = query.where(TaskInstance.status == "completed")
    else:
        query = query.where(TaskInstance.status != "completed")
    if view == "recurring":
        query = query.where(TaskDefinition.repeat_rule["kind"].as_string() != "none")
    if category:
        query = query.where(TaskDefinition.category == category)
    if room:
        query = query.where(TaskDefinition.room == room)
    if task_status:
        query = query.where(TaskInstance.status == task_status)
    if user_id:
        query = query.outerjoin(TaskAssignment).where(
            or_(TaskInstance.assignee_id == user_id, TaskAssignment.user_id == user_id)
        )
    instances = list(
        await db.scalars(query.order_by(TaskInstance.due_at.asc().nulls_last()).distinct())
    )
    return [read_task(item) for item in instances]


@router.get("/today", response_model=list[TaskRead])
async def today_tasks(
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    scope: str = Query(default="mine", pattern="^(mine|all)$"),
) -> list[TaskRead]:
    timezone = await household_timezone(db, auth.user.household_id)
    now_local = datetime.now(timezone)
    start = datetime.combine(now_local.date(), time.min, timezone).astimezone(UTC)
    end = datetime.combine(now_local.date() + timedelta(days=1), time.min, timezone).astimezone(
        UTC
    ) - timedelta(microseconds=1)
    query = (
        select(TaskInstance)
        .join(TaskDefinition)
        .outerjoin(TaskAssignment)
        .options(selectinload(TaskInstance.task).options(*task_options()))
        .where(
            TaskDefinition.household_id == auth.user.household_id,
            or_(TaskInstance.due_at <= end, TaskInstance.due_at.is_(None)),
        )
    )
    if scope == "mine":
        query = query.where(
            or_(
                TaskInstance.assignee_id == auth.user.id,
                TaskAssignment.user_id == auth.user.id,
                TaskDefinition.assignment_mode == "anyone",
            )
        )
    instances = list(await db.scalars(query.order_by(TaskInstance.due_at).distinct()))
    completed_today = [
        item
        for item in instances
        if item.status != "completed"
        or (item.completed_at is not None and item.completed_at >= start)
    ]
    return [read_task(item) for item in completed_today]


def can_complete(auth: AuthContext, instance: TaskInstance) -> bool:
    if auth.user.role != UserRole.CHILD:
        return True
    task = instance.task
    assigned = {assignment.user_id for assignment in task.assignments}
    return (
        task.assignment_mode == "anyone"
        or instance.assignee_id == auth.user.id
        or auth.user.id in assigned
    )


@router.post("/{instance_id}/complete", response_model=TaskRead)
async def complete_task(
    instance_id: str,
    payload: TaskComplete,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskRead:
    instance = await load_instance(db, instance_id, auth.user.household_id)
    if instance.status not in {"open", "rejected"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Дело уже обработано")
    if not can_complete(auth, instance):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Дело назначено другому")
    if instance.task.requires_photo and not payload.photo_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Нужно фото")
    instance.subtask_state = {
        subtask.id: subtask.id in payload.completed_subtask_ids
        for subtask in instance.task.subtasks
    }
    if instance.task.subtasks and not all(instance.subtask_state.values()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Завершите все подзадачи",
        )
    completed_at = now_utc()
    instance.completed_by_id = auth.user.id
    instance.completion_photo_id = payload.photo_id
    instance.completion_comment = payload.comment.strip() if payload.comment else None
    instance.completion_cost = payload.actual_cost
    instance.completion_photo_ids = list(
        dict.fromkeys(payload.photo_ids + ([payload.photo_id] if payload.photo_id else []))
    )
    if auth.user.role == UserRole.CHILD and instance.task.requires_adult_review:
        instance.status = "awaiting_review"
        action = "submitted_for_review"
    else:
        instance.status = "completed"
        instance.completed_at = completed_at
        action = "completed"
        if instance.task.assignment_mode == "queue" and instance.task.queue:
            instance.task.current_queue_index = (instance.task.current_queue_index + 1) % len(
                instance.task.queue
            )
        await build_next_instance(db, instance.task, instance, completed_at)
        if instance.task.source_type == "maintenance":
            from app.services.home import record_completed_maintenance

            await record_completed_maintenance(db, instance.task, instance, completed_at)
    db.add(
        TaskHistory(
            task_id=instance.task.id,
            instance_id=instance.id,
            actor_id=auth.user.id,
            action=action,
            happened_at=completed_at,
        )
    )
    await db.commit()
    return read_task(await load_instance(db, instance.id, auth.user.household_id))


@router.post("/{instance_id}/review", response_model=TaskRead)
async def review_task(
    instance_id: str,
    payload: TaskReview,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskRead:
    ensure_adult(auth)
    instance = await load_instance(db, instance_id, auth.user.household_id)
    if instance.status != "awaiting_review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Дело не ждёт проверки")
    instance.review_comment = payload.comment.strip() if payload.comment else None
    happened_at = now_utc()
    if payload.decision == "approve":
        instance.status = "completed"
        instance.completed_at = happened_at
        if instance.task.assignment_mode == "queue" and instance.task.queue:
            instance.task.current_queue_index = (instance.task.current_queue_index + 1) % len(
                instance.task.queue
            )
        await build_next_instance(db, instance.task, instance, happened_at)
        if instance.task.source_type == "maintenance":
            from app.services.home import record_completed_maintenance

            await record_completed_maintenance(db, instance.task, instance, happened_at)
    else:
        instance.status = "rejected"
        instance.completed_at = None
    db.add(
        TaskHistory(
            task_id=instance.task.id,
            instance_id=instance.id,
            actor_id=auth.user.id,
            action=f"review_{payload.decision}",
            note=instance.review_comment,
            happened_at=happened_at,
        )
    )
    await db.commit()
    return read_task(await load_instance(db, instance.id, auth.user.household_id))


@router.post("/{instance_id}/skip-queue", response_model=TaskRead)
async def skip_queue(
    instance_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskRead:
    if auth.user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Нужны права администратора"
        )
    instance = await load_instance(db, instance_id, auth.user.household_id)
    if instance.task.assignment_mode != "queue" or not instance.task.queue:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="У дела нет очереди")
    instance.task.current_queue_index = (instance.task.current_queue_index + 1) % len(
        instance.task.queue
    )
    local_date = (instance.due_at or now_utc()).date()
    instance.assignee_id, instance.task.current_queue_index = await queue_assignee(
        db, instance.task, on_date=local_date
    )
    db.add(
        TaskHistory(
            task_id=instance.task.id,
            instance_id=instance.id,
            actor_id=auth.user.id,
            action="queue_skipped",
            happened_at=now_utc(),
        )
    )
    await db.commit()
    return read_task(await load_instance(db, instance.id, auth.user.household_id))


@router.get("/{definition_id}/history", response_model=list[TaskHistoryRead])
async def task_history(
    definition_id: str,
    auth: Annotated[AuthContext, Depends(current_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[TaskHistoryRead]:
    exists = await db.scalar(
        select(TaskDefinition.id).where(
            TaskDefinition.id == definition_id,
            TaskDefinition.household_id == auth.user.household_id,
        )
    )
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Дело не найдено")
    items = await db.scalars(
        select(TaskHistory)
        .where(TaskHistory.task_id == definition_id)
        .order_by(TaskHistory.happened_at.desc())
    )
    return [TaskHistoryRead.model_validate(item) for item in items]


@router.delete("/{definition_id}", response_model=Message)
async def archive_task(
    definition_id: str,
    auth: Annotated[AuthContext, Depends(csrf_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Message:
    ensure_adult(auth)
    task = await db.scalar(
        select(TaskDefinition).where(
            TaskDefinition.id == definition_id,
            TaskDefinition.household_id == auth.user.household_id,
        )
    )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Дело не найдено")
    task.is_active = False
    await db.commit()
    return Message(message="Дело перенесено в архив")
