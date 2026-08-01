from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CalendarEvent(BaseModel):
    id: str
    source_type: Literal["task", "shopping", "maintenance", "meter", "warranty", "storage"]
    source_id: str
    title: str
    starts_at: datetime
    status: str
    user_ids: list[str]
    scope: Literal["personal", "shared"]
    editable: bool
    recurring: bool = False


class CalendarMove(BaseModel):
    source_type: Literal["task", "shopping", "maintenance", "meter", "warranty", "storage"]
    source_id: str
    starts_at: datetime
    recurrence_scope: Literal["instance", "series"] = "instance"
