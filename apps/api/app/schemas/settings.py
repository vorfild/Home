from __future__ import annotations

from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import ApiModel

EVENT_TYPES = (
    "task_assigned",
    "task_due",
    "task_overdue",
    "queue_turn",
    "shopping_today",
    "shopping_changed",
    "storage_review",
    "maintenance_due",
    "meter_due",
    "warranty_expiring",
)


class PreferenceUpdate(BaseModel):
    channels: dict[str, bool] = Field(
        default_factory=lambda: {"in_app": True, "push": False, "email": False}
    )
    event_rules: dict[str, bool] = Field(default_factory=dict)
    reminder_minutes: int = Field(default=60, ge=0, le=60 * 24 * 30)
    repeat_minutes: int | None = Field(default=None, ge=15, le=60 * 24 * 7)
    quiet_start: time | None = None
    quiet_end: time | None = None
    email: str | None = Field(default=None, max_length=254)
    theme: Literal["system", "light", "dark"] = "system"
    font_scale: Literal["small", "normal", "large"] = "normal"
    density: Literal["compact", "comfortable"] = "comfortable"

    @model_validator(mode="after")
    def complete_quiet_hours(self) -> PreferenceUpdate:
        if (self.quiet_start is None) != (self.quiet_end is None):
            raise ValueError("Укажите начало и конец тихих часов")
        self.channels = {
            "in_app": bool(self.channels.get("in_app", True)),
            "push": bool(self.channels.get("push", False)),
            "email": bool(self.channels.get("email", False)),
        }
        self.event_rules = {key: bool(self.event_rules.get(key, True)) for key in EVENT_TYPES}
        if self.channels["email"] and self.email is None:
            raise ValueError("Для email-уведомлений нужен адрес")
        if self.email and ("@" not in self.email or self.email.startswith("@")):
            raise ValueError("Некорректный email")
        return self


class PreferenceRead(PreferenceUpdate):
    model_config = ConfigDict(from_attributes=True)

    user_id: str


class ModuleSettings(BaseModel):
    meters: bool = True
    email: bool = False
    shopping_prices: bool = True
    maintenance_finances: bool = True
    task_photos: bool = True


class ServerSettingsUpdate(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)
    domain: str | None = Field(default=None, max_length=255)


class ServerSettingsRead(ServerSettingsUpdate):
    https_enabled: bool
    files_dir: str
    app_version: str
    web_push_configured: bool
    smtp_configured: bool


class NotificationRead(ApiModel):
    id: str
    event_type: str
    title: str
    body: str
    source_type: str | None
    source_id: str | None
    read_at: datetime | None
    created_at: datetime


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(min_length=10, max_length=4096)
    p256dh: str = Field(min_length=10, max_length=512)
    auth: str = Field(min_length=5, max_length=512)


class PushKey(BaseModel):
    enabled: bool
    public_key: str | None


class FamilyStats(BaseModel):
    user_id: str
    today_tasks: int
    overdue_tasks: int
    queue_tasks: int
    awaiting_review: int
    pending_requests: int
