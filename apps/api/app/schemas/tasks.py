from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ApiModel

Priority = Literal["low", "normal", "high", "urgent"]
AssignmentMode = Literal["fixed", "anyone", "multiple", "queue"]


class RepeatRule(BaseModel):
    kind: Literal[
        "none",
        "daily",
        "weekdays",
        "weekly",
        "monthly",
        "yearly",
        "interval",
        "after_completion",
        "day_of_month",
        "seasonal",
    ] = "none"
    interval: int = Field(default=1, ge=1, le=365)
    unit: Literal["days", "weeks", "months", "years"] = "days"
    weekdays: list[int] = Field(default_factory=list)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    months: list[int] = Field(default_factory=list)

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Дни недели должны быть от 0 до 6")
        return sorted(set(value))


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    room: str | None = Field(default=None, max_length=100)
    category: str = Field(default="другое", min_length=1, max_length=80)
    due_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=1, le=1440)
    priority: Priority = "normal"
    assignment_mode: AssignmentMode = "fixed"
    assignee_ids: list[str] = Field(default_factory=list)
    queue_user_ids: list[str] = Field(default_factory=list)
    subtasks: list[str] = Field(default_factory=list, max_length=100)
    repeat: RepeatRule = Field(default_factory=RepeatRule)
    reminders: list[dict[str, Any]] = Field(default_factory=list)
    requires_photo: bool = False
    requires_adult_review: bool = False

    @model_validator(mode="after")
    def validate_assignment(self) -> TaskCreate:
        assignees = list(dict.fromkeys(self.assignee_ids))
        queue = list(dict.fromkeys(self.queue_user_ids))
        self.assignee_ids = assignees
        self.queue_user_ids = queue
        if self.assignment_mode == "fixed" and len(assignees) != 1:
            raise ValueError("Для закреплённого дела нужен один ответственный")
        if self.assignment_mode == "multiple" and len(assignees) < 2:
            raise ValueError("Для совместного дела нужны минимум два ответственных")
        if self.assignment_mode == "queue" and len(queue) < 2:
            raise ValueError("В очереди нужны минимум два участника")
        return self


class TaskRead(ApiModel):
    id: str
    definition_id: str
    title: str
    description: str | None
    room: str | None
    category: str
    due_at: datetime | None
    estimated_minutes: int | None
    priority: str
    assignment_mode: str
    assignee_ids: list[str]
    queue_user_ids: list[str]
    current_queue_user_id: str | None
    next_queue_user_id: str | None
    subtasks: list[dict[str, Any]]
    repeat: dict[str, Any]
    requires_photo: bool
    requires_adult_review: bool
    status: str
    completed_by_id: str | None
    completed_at: datetime | None
    review_comment: str | None


class TaskComplete(BaseModel):
    photo_id: str | None = None
    completed_subtask_ids: list[str] = Field(default_factory=list)


class TaskReview(BaseModel):
    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def rejection_needs_comment(self) -> TaskReview:
        if self.decision == "reject" and not (self.comment or "").strip():
            raise ValueError("При отклонении укажите комментарий")
        return self


class TaskHistoryRead(ApiModel):
    action: str
    actor_id: str | None
    note: str | None
    happened_at: datetime
