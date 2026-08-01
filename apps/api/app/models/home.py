from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.identity import new_id


class Equipment(TimestampMixin, Base):
    __tablename__ = "equipment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    storage_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("storage_items.id", ondelete="SET NULL"), unique=True, index=True
    )
    name: Mapped[str | None] = mapped_column(String(180), index=True)
    photo_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    location: Mapped[str | None] = mapped_column(String(180))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(160), index=True)
    acquired_on: Mapped[date | None] = mapped_column(Date)
    warranty_until: Mapped[date | None] = mapped_column(Date, index=True)
    document_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    condition: Mapped[str] = mapped_column(String(40), default="working", index=True)
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    plans: Mapped[list[MaintenancePlan]] = relationship(
        back_populates="equipment", cascade="all, delete-orphan"
    )


class MaintenancePlan(TimestampMixin, Base):
    __tablename__ = "maintenance_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_on: Mapped[date | None] = mapped_column(Date)
    next_on: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    checklist: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    materials: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    open_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_instances.id", ondelete="SET NULL"), unique=True
    )

    equipment: Mapped[Equipment | None] = relationship(back_populates="plans")


class MaintenanceRecord(TimestampMixin, Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (UniqueConstraint("task_instance_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    equipment_id: Mapped[str | None] = mapped_column(
        ForeignKey("equipment.id", ondelete="SET NULL"), index=True
    )
    plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("maintenance_plans.id", ondelete="SET NULL"), index=True
    )
    task_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_instances.id", ondelete="SET NULL"), index=True
    )
    record_type: Mapped[str] = mapped_column(String(24), default="repair", index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    performed_on: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    photo_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    attachment_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    keep_forever: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Meter(TimestampMixin, Base):
    __tablename__ = "meters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), index=True
    )
    meter_type: Mapped[str] = mapped_column(String(80), index=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(160), index=True)
    location: Mapped[str | None] = mapped_column(String(180))
    last_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    next_submission_on: Mapped[date | None] = mapped_column(Date, index=True)
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reset_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    open_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_instances.id", ondelete="SET NULL"), unique=True
    )

    readings: Mapped[list[MeterReading]] = relationship(
        back_populates="meter", cascade="all, delete-orphan"
    )


class MeterReading(TimestampMixin, Base):
    __tablename__ = "meter_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    read_on: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    photo_id: Mapped[str | None] = mapped_column(String(36))
    comment: Mapped[str | None] = mapped_column(Text)
    consumption: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    decrease_warning: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reset_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    meter: Mapped[Meter] = relationship(back_populates="readings")
