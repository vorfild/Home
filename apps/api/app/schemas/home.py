from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ApiModel


class EquipmentCreate(BaseModel):
    storage_item_id: str | None = None
    name: str | None = Field(default=None, max_length=180)
    photo_ids: list[str] = Field(default_factory=list)
    category: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=180)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=160)
    acquired_on: date | None = None
    warranty_until: date | None = None
    document_ids: list[str] = Field(default_factory=list)
    condition: str = Field(default="working", max_length=40)
    responsible_id: str | None = None

    @model_validator(mode="after")
    def identity_source(self) -> EquipmentCreate:
        if not self.storage_item_id and not (self.name or "").strip():
            raise ValueError("Укажите название или карточку кладовой")
        return self


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=180)
    photo_ids: list[str] | None = None
    category: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=180)
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=160)
    acquired_on: date | None = None
    warranty_until: date | None = None
    document_ids: list[str] | None = None
    condition: str | None = Field(default=None, max_length=40)
    responsible_id: str | None = None


class EquipmentRead(ApiModel):
    id: str
    storage_item_id: str | None
    name: str
    photo_ids: list[str]
    category: str | None
    location: str | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    acquired_on: date | None
    warranty_until: date | None
    document_ids: list[str]
    condition: str
    responsible_id: str | None


class MaintenanceCreate(BaseModel):
    equipment_id: str | None = None
    title: str = Field(min_length=1, max_length=180)
    interval_days: int = Field(ge=1, le=3650)
    previous_on: date | None = None
    next_on: date
    responsible_id: str | None = None
    checklist: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    requires_photo: bool = False


class MaintenanceRead(ApiModel):
    id: str
    equipment_id: str | None
    title: str
    interval_days: int
    previous_on: date | None
    next_on: date
    responsible_id: str | None
    checklist: list[str]
    materials: list[str]
    estimated_cost: Decimal | None
    requires_photo: bool
    is_active: bool
    open_task_id: str | None


class MaintenanceComplete(BaseModel):
    performed_on: date = Field(default_factory=date.today)
    comment: str | None = Field(default=None, max_length=5000)
    actual_cost: Decimal | None = Field(default=None, ge=0)
    photo_ids: list[str] = Field(default_factory=list)


class RepairCreate(BaseModel):
    equipment_id: str | None = None
    title: str = Field(min_length=1, max_length=180)
    performed_on: date
    comment: str | None = Field(default=None, max_length=5000)
    actual_cost: Decimal | None = Field(default=None, ge=0)
    photo_ids: list[str] = Field(default_factory=list)
    attachment_ids: list[str] = Field(default_factory=list)
    keep_forever: bool = False


class RepairRead(ApiModel):
    id: str
    equipment_id: str | None
    plan_id: str | None
    task_instance_id: str | None
    record_type: str
    title: str
    performed_on: date
    comment: str | None
    actual_cost: Decimal | None
    photo_ids: list[str]
    attachment_ids: list[str]
    keep_forever: bool
    purge_after: datetime | None


class MeterCreate(BaseModel):
    meter_type: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=32)
    serial_number: str | None = Field(default=None, max_length=160)
    location: str | None = Field(default=None, max_length=180)
    next_submission_on: date | None = None
    responsible_id: str | None = None


class MeterRead(ApiModel):
    id: str
    meter_type: str
    unit: str
    serial_number: str | None
    location: str | None
    last_value: Decimal | None
    next_submission_on: date | None
    responsible_id: str | None
    reset_sequence: int
    is_active: bool


class ReadingCreate(BaseModel):
    value: Decimal = Field(ge=0)
    read_on: date = Field(default_factory=date.today)
    photo_id: str | None = None
    comment: str | None = Field(default=None, max_length=5000)
    accept_decrease: bool = False
    next_submission_on: date | None = None


class ReadingRead(ApiModel):
    id: str
    meter_id: str
    value: Decimal
    read_on: date
    photo_id: str | None
    comment: str | None
    consumption: Decimal | None
    decrease_warning: bool
    reset_sequence: int


class MeterReplace(BaseModel):
    serial_number: str | None = Field(default=None, max_length=160)
    start_value: Decimal = Field(default=Decimal("0"), ge=0)
    replaced_on: date = Field(default_factory=date.today)
    comment: str | None = Field(default=None, max_length=5000)


class ModuleToggle(BaseModel):
    enabled: bool


class HomeOverview(BaseModel):
    meters_enabled: bool
    maintenance_due: list[MaintenanceRead]
    warranties_expiring: list[EquipmentRead]
    meter_deadlines: list[MeterRead]
    equipment_attention: list[EquipmentRead]


class HistoryFilter(BaseModel):
    record_type: Literal["all", "repair", "maintenance"] = "all"
