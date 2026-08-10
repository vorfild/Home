from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ApiModel


class StorageNodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parent_id: str | None = None
    node_type: str = Field(default="другое", min_length=1, max_length=40)
    sort_order: int = Field(default=0, ge=0)


class StorageNodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    parent_id: str | None = None
    node_type: str | None = Field(default=None, min_length=1, max_length=40)
    sort_order: int | None = Field(default=None, ge=0)


class StorageNodeRead(ApiModel):
    id: str
    parent_id: str | None
    name: str
    node_type: str
    sort_order: int
    path: list[dict[str, str]] = Field(default_factory=list)
    has_qr: bool = False


class StorageItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    node_id: str
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=80)
    owner_id: str | None = None
    description: str | None = Field(default=None, max_length=10000)
    tags: list[str] = Field(default_factory=list, max_length=100)
    item_status: Literal[
        "stored", "in_use", "borrowed_temporarily", "lent", "lost", "sold", "given", "discarded"
    ] = "stored"
    placed_at: date | None = None
    last_used_at: date | None = None
    value: Decimal | None = Field(default=None, ge=0)
    purchased_on: date | None = None
    manufacturer: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=160)
    warranty_until: date | None = None
    comment: str | None = Field(default=None, max_length=10000)
    review_at: datetime | None = None


class StorageItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    node_id: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    unit: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=80)
    owner_id: str | None = None
    description: str | None = Field(default=None, max_length=10000)
    tags: list[str] | None = Field(default=None, max_length=100)
    item_status: str | None = None
    review_at: datetime | None = None
    comment: str | None = Field(default=None, max_length=10000)


class StorageItemRead(ApiModel):
    id: str
    node_id: str
    name: str
    photo_ids: list[str]
    primary_photo_id: str | None
    quantity: Decimal | None
    unit: str | None
    category: str | None
    owner_id: str | None
    description: str | None
    tags: list[str]
    item_status: str
    placed_at: date | None
    location_since: datetime
    last_used_at: date | None
    value: Decimal | None
    purchased_on: date | None
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    warranty_until: date | None
    comment: str | None
    review_at: datetime | None
    review_status: str
    path: list[dict[str, str]] = Field(default_factory=list)


class StorageContents(BaseModel):
    node: StorageNodeRead | None
    children: list[StorageNodeRead]
    items: list[StorageItemRead]


class QrRead(BaseModel):
    node_id: str
    token: str
    path: str


class StorageSearchResult(BaseModel):
    items: list[StorageItemRead]
    nodes: list[StorageNodeRead]


class BulkStorageAction(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=1000)
    action: Literal["move", "category", "owner", "timer", "archive"]
    node_id: str | None = None
    category: str | None = None
    owner_id: str | None = None
    review_at: datetime | None = None
    timer_days: int | None = Field(default=None, ge=1, le=36500)

    @model_validator(mode="after")
    def action_value(self) -> BulkStorageAction:
        required = {
            "move": self.node_id,
            "category": self.category,
            "owner": self.owner_id,
            "timer": self.review_at or self.timer_days,
            "archive": True,
        }
        if not required[self.action]:
            raise ValueError("Не указано значение группового действия")
        return self


class StorageTimerExtend(BaseModel):
    days: int = Field(ge=1, le=36500)


class DeleteNodeRequest(BaseModel):
    strategy: Literal["move", "delete"]
    target_node_id: str | None = None
    file_action: Literal["keep", "delete"] = "keep"

    @model_validator(mode="after")
    def move_target(self) -> DeleteNodeRequest:
        if self.strategy == "move" and not self.target_node_id:
            raise ValueError("Выберите раздел для переноса")
        return self
