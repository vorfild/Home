from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class EntityVersionRead(BaseModel):
    entity_type: str
    entity_id: str
    version: int
    state: dict[str, Any]
    updated_at: datetime
    changed_by_id: str | None
    has_conflict: bool = False


class SyncChange(BaseModel):
    client_operation_id: str = Field(min_length=8, max_length=64)
    entity_type: Literal[
        "task", "shopping_item", "storage_item", "equipment", "maintenance", "meter"
    ]
    entity_id: str
    base_version: int = Field(ge=1)
    changes: dict[str, Any] = Field(min_length=1, max_length=30)


class SyncChangeResult(BaseModel):
    status: Literal["applied", "merged", "conflict"]
    version: int
    state: dict[str, Any]
    conflict_ids: list[str] = Field(default_factory=list)


class SyncConflictRead(ApiModel):
    id: str
    entity_type: str
    entity_id: str
    field_name: str
    base_version: int
    server_version: int
    server_value: Any
    alternative_value: Any
    proposed_by_id: str
    status: str
    created_at: datetime


class ConflictResolution(BaseModel):
    resolution: Literal["server", "alternative", "manual"]
    manual_value: Any = None


class SyncEventRead(ApiModel):
    sequence: int
    entity_type: str
    entity_id: str
    action: str
    changed_fields: list[str]
    actor_id: str | None
    version: int | None
    created_at: datetime


class EntityConflictStatus(BaseModel):
    entity_type: str
    entity_id: str
    count: int
    latest_changed_at: datetime
    latest_actor_id: str
