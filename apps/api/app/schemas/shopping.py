from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ApiModel


class ShoppingListCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    store: str | None = Field(default=None, max_length=120)
    scheduled_at: datetime | None = None
    responsible_id: str | None = None
    comment: str | None = Field(default=None, max_length=5000)


class ShoppingItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(default="шт.", min_length=1, max_length=32)
    category: str = Field(default="другое", min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    recipient_id: str | None = None
    photo_id: str | None = None
    price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    store: str | None = Field(default=None, max_length=120)
    client_operation_id: str | None = Field(default=None, min_length=8, max_length=64)


class ShoppingItemRead(ApiModel):
    id: str
    list_id: str
    name: str
    quantity: Decimal
    unit: str
    category: str
    note: str | None
    added_by_id: str | None
    recipient_id: str | None
    purchased: bool
    photo_id: str | None
    price: Decimal | None
    store: str | None
    proposal_status: str
    duplicate_warning: bool = False


class ShoppingListRead(ApiModel):
    id: str
    title: str
    store: str | None
    scheduled_at: datetime | None
    responsible_id: str | None
    status: str
    comment: str | None
    completed_at: datetime | None
    items: list[ShoppingItemRead]
    total: Decimal | None = None


class ShoppingItemUpdate(BaseModel):
    purchased: bool | None = None
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    note: str | None = Field(default=None, max_length=500)


class ProposalDecision(BaseModel):
    decision: Literal["accept", "reject"]


class ShoppingListComplete(BaseModel):
    unpurchased: Literal["keep", "move", "remove"]
    target_list_id: str | None = None

    @model_validator(mode="after")
    def move_needs_target(self) -> ShoppingListComplete:
        if self.unpurchased == "move" and not self.target_list_id:
            raise ValueError("Выберите список для переноса")
        return self


class FrequentItem(BaseModel):
    name: str
    category: str
    unit: str
    count: int
