from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel


class FileRead(ApiModel):
    id: str
    entity_type: str
    entity_id: str
    purpose: str
    original_name: str
    original_mime: str
    stored_mime: str
    size_bytes: int
    width: int | None
    height: int | None
    is_primary: bool
    created_at: datetime


class BackupRead(ApiModel):
    id: str
    kind: Literal["monthly", "manual", "insurance"]
    checksum: str
    size_bytes: int
    app_version: str
    schema_version: str
    status: str
    manifest: dict[str, Any]
    verified_at: datetime
    created_at: datetime


class DataStatus(BaseModel):
    monthly: BackupRead | None
    manual: list[BackupRead]
    insurance: list[BackupRead]
    files_bytes: int
    backups_bytes: int
    app_version: str
    schema_version: str


class RestoreRead(ApiModel):
    id: str
    status: str
    source_name: str
    source_checksum: str
    counts_before: dict[str, int]
    counts_after: dict[str, int]
    warnings: list[str]
    details: str | None
    created_at: datetime
    completed_at: datetime | None


class UpdatePrepare(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    target_ref: str = Field(min_length=7, max_length=120, pattern=r"^[A-Za-z0-9._/-]+$")


class UpdatePlan(BaseModel):
    current_version: str
    target_ref: str
    insurance_backup_id: str
    command: str
    rollback_command: str
