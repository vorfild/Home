from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class CatalogCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=10000)
    color: str = Field(default="#8DB8A8", pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str = Field(default="tag", min_length=1, max_length=40)


class CatalogUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    sort_order: int | None = Field(default=None, ge=0, le=10000)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: str | None = Field(default=None, min_length=1, max_length=40)
    is_active: bool | None = None


class RoomRead(ApiModel):
    id: str
    name: str
    sort_order: int
    color: str
    icon: str
    is_active: bool


class CategoryRead(RoomRead):
    domain: Literal["task", "shopping", "storage"]
    is_default: bool


class TrashCreate(BaseModel):
    file_action: Literal["keep", "delete"]


class TrashRead(ApiModel):
    id: str
    entity_type: str
    entity_id: str
    title: str
    deleted_by_id: str | None
    deleted_at: datetime
    purge_after: datetime
    file_action: str


class ArchiveRead(BaseModel):
    entity_type: str
    entity_id: str
    title: str
    archived_at: datetime
    detail: str
