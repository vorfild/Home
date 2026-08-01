from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.identity import new_id


class StorageNode(TimestampMixin, Base):
    __tablename__ = "storage_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("storage_nodes.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    node_type: Mapped[str] = mapped_column(String(40), default="другое", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    qr_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    qr_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    parent: Mapped[StorageNode | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[StorageNode]] = relationship(back_populates="parent")
    items: Mapped[list[StorageItem]] = relationship(back_populates="node")


class StorageItem(TimestampMixin, Base):
    __tablename__ = "storage_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True, nullable=False
    )
    node_id: Mapped[str] = mapped_column(
        ForeignKey("storage_nodes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    photo_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    primary_photo_id: Mapped[str | None] = mapped_column(String(36))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    owner_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    item_status: Mapped[str] = mapped_column(String(24), default="stored", index=True)
    placed_at: Mapped[date | None] = mapped_column(Date)
    location_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[date | None] = mapped_column(Date)
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    purchased_on: Mapped[date | None] = mapped_column(Date)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(160), index=True)
    warranty_until: Mapped[date | None] = mapped_column(Date)
    comment: Mapped[str | None] = mapped_column(Text)
    review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    review_status: Mapped[str] = mapped_column(String(20), default="none", index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    node: Mapped[StorageNode] = relationship(back_populates="items")
