from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.identity import new_id


class SyncEvent(Base):
    __tablename__ = "sync_events"

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    entity_id: Mapped[str] = mapped_column(String(120), index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )


class EntityVersion(TimestampMixin, Base):
    __tablename__ = "entity_versions"
    __table_args__ = (UniqueConstraint("household_id", "entity_type", "entity_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    field_versions: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    last_actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class SyncOperation(Base):
    __tablename__ = "sync_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_operation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(48), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_status: Mapped[str] = mapped_column(String(24), nullable=False)
    result_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SyncConflict(TimestampMixin, Base):
    __tablename__ = "sync_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(48), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    field_name: Mapped[str] = mapped_column(String(80), index=True)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    server_version: Mapped[int] = mapped_column(Integer, nullable=False)
    server_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    alternative_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    proposed_by_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    resolved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(20))
    manual_value: Mapped[Any] = mapped_column(JSON, nullable=True)
