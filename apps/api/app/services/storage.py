from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.storage import StorageItem
from app.models.tasks import TaskDefinition, TaskInstance
from app.services.auth import now_utc


async def process_storage_timers(db: AsyncSession) -> int:
    now = now_utc()
    expired = list(
        await db.scalars(
            select(StorageItem).where(
                StorageItem.review_at.is_not(None),
                StorageItem.review_at <= now,
                StorageItem.review_status == "active",
                StorageItem.archived_at.is_(None),
            )
        )
    )
    created = 0
    for item in expired:
        item.review_status = "decision_required"
        task = await db.scalar(
            select(TaskDefinition).where(
                TaskDefinition.source_type == "storage_review",
                TaskDefinition.source_id == item.id,
                TaskDefinition.is_active.is_(True),
            )
        )
        if task is None:
            task = TaskDefinition(
                household_id=item.household_id,
                title=f"Решить, что делать: {item.name}",
                description="Истёк заданный срок хранения вещи.",
                category="обслуживание",
                priority="normal",
                assignment_mode="anyone",
                repeat_rule={"kind": "none"},
                reminders=[],
                source_type="storage_review",
                source_id=item.id,
            )
            db.add(task)
            await db.flush()
            db.add(
                TaskInstance(
                    task_id=task.id,
                    sequence=1,
                    due_at=now,
                    status="open",
                    subtask_state={},
                )
            )
            created += 1
    return created
