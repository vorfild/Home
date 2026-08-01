from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.identity import new_id


class TaskDefinition(TimestampMixin, Base):
    __tablename__ = "task_definitions"
    __table_args__ = (Index("uq_task_definitions_source", "source_type", "source_id", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    room: Mapped[str | None] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(80), default="другое", index=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(12), default="normal", index=True)
    assignment_mode: Mapped[str] = mapped_column(String(12), default="fixed")
    repeat_rule: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reminders: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_adult_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_queue_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(40), index=True)
    source_id: Mapped[str | None] = mapped_column(String(36), index=True)

    assignments: Mapped[list[TaskAssignment]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskAssignment.position"
    )
    queue: Mapped[list[TaskQueueMember]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskQueueMember.position"
    )
    subtasks: Mapped[list[TaskSubtask]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="TaskSubtask.position"
    )
    instances: Mapped[list[TaskInstance]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskAssignment(Base):
    __tablename__ = "task_assignments"
    __table_args__ = (UniqueConstraint("task_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    task: Mapped[TaskDefinition] = relationship(back_populates="assignments")


class TaskQueueMember(Base):
    __tablename__ = "task_queue_members"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id"),
        UniqueConstraint("task_id", "position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    task: Mapped[TaskDefinition] = relationship(back_populates="queue")


class TaskSubtask(Base):
    __tablename__ = "task_subtasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    task: Mapped[TaskDefinition] = relationship(back_populates="subtasks")


class TaskInstance(TimestampMixin, Base):
    __tablename__ = "task_instances"
    __table_args__ = (UniqueConstraint("task_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    completed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completion_photo_id: Mapped[str | None] = mapped_column(String(36))
    review_comment: Mapped[str | None] = mapped_column(String(500))
    subtask_state: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict, nullable=False)

    task: Mapped[TaskDefinition] = relationship(back_populates="instances")


class TaskHistory(Base):
    __tablename__ = "task_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("task_definitions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_instances.id", ondelete="SET NULL"), index=True
    )
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    happened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
