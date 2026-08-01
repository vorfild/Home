"""Add home equipment, maintenance, repair history and meters.

Revision ID: 0006_home
Revises: 0005_storage
Create Date: 2026-08-01 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_home"
down_revision: str | None = "0005_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column[sa.DateTime], sa.Column[sa.DateTime]]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.add_column(
        "households",
        sa.Column("meters_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("task_instances", sa.Column("completion_comment", sa.Text(), nullable=True))
    op.add_column("task_instances", sa.Column("completion_cost", sa.Numeric(14, 2), nullable=True))
    op.add_column(
        "task_instances",
        sa.Column("completion_photo_ids", sa.JSON(), server_default="[]", nullable=False),
    )
    op.create_table(
        "equipment",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("storage_item_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(180), nullable=True),
        sa.Column("photo_ids", sa.JSON(), nullable=False),
        sa.Column("category", sa.String(80), nullable=True),
        sa.Column("location", sa.String(180), nullable=True),
        sa.Column("manufacturer", sa.String(120), nullable=True),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("serial_number", sa.String(160), nullable=True),
        sa.Column("acquired_on", sa.Date(), nullable=True),
        sa.Column("warranty_until", sa.Date(), nullable=True),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("condition", sa.String(40), nullable=False),
        sa.Column("responsible_id", sa.String(36), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["storage_item_id"], ["storage_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsible_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("storage_item_id"),
    )
    for column in (
        "household_id",
        "storage_item_id",
        "name",
        "category",
        "serial_number",
        "warranty_until",
        "condition",
        "responsible_id",
        "archived_at",
    ):
        op.create_index(f"ix_equipment_{column}", "equipment", [column])
    op.create_table(
        "maintenance_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("equipment_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("previous_on", sa.Date(), nullable=True),
        sa.Column("next_on", sa.Date(), nullable=False),
        sa.Column("responsible_id", sa.String(36), nullable=True),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("requires_photo", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("open_task_id", sa.String(36), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["open_task_id"], ["task_instances.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("open_task_id"),
    )
    for column in ("household_id", "equipment_id", "next_on", "responsible_id"):
        op.create_index(f"ix_maintenance_plans_{column}", "maintenance_plans", [column])
    op.create_table(
        "maintenance_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("equipment_id", sa.String(36), nullable=True),
        sa.Column("plan_id", sa.String(36), nullable=True),
        sa.Column("task_instance_id", sa.String(36), nullable=True),
        sa.Column("record_type", sa.String(24), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actual_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("photo_ids", sa.JSON(), nullable=False),
        sa.Column("attachment_ids", sa.JSON(), nullable=False),
        sa.Column("keep_forever", sa.Boolean(), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_id"], ["equipment.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_id"], ["maintenance_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_instance_id"], ["task_instances.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("task_instance_id"),
    )
    for column in (
        "household_id",
        "equipment_id",
        "plan_id",
        "task_instance_id",
        "record_type",
        "performed_on",
        "purge_after",
    ):
        op.create_index(f"ix_maintenance_records_{column}", "maintenance_records", [column])
    op.create_table(
        "meters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("meter_type", sa.String(80), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("serial_number", sa.String(160), nullable=True),
        sa.Column("location", sa.String(180), nullable=True),
        sa.Column("last_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("next_submission_on", sa.Date(), nullable=True),
        sa.Column("responsible_id", sa.String(36), nullable=True),
        sa.Column("reset_sequence", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("open_task_id", sa.String(36), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["open_task_id"], ["task_instances.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("open_task_id"),
    )
    for column in (
        "household_id",
        "meter_type",
        "serial_number",
        "next_submission_on",
        "responsible_id",
    ):
        op.create_index(f"ix_meters_{column}", "meters", [column])
    op.create_table(
        "meter_readings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meter_id", sa.String(36), nullable=False),
        sa.Column("value", sa.Numeric(18, 4), nullable=False),
        sa.Column("read_on", sa.Date(), nullable=False),
        sa.Column("photo_id", sa.String(36), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("consumption", sa.Numeric(18, 4), nullable=True),
        sa.Column("decrease_warning", sa.Boolean(), nullable=False),
        sa.Column("reset_sequence", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["meter_id"], ["meters.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_meter_readings_meter_id", "meter_readings", ["meter_id"])
    op.create_index("ix_meter_readings_read_on", "meter_readings", ["read_on"])


def downgrade() -> None:
    op.drop_table("meter_readings")
    op.drop_table("meters")
    op.drop_table("maintenance_records")
    op.drop_table("maintenance_plans")
    op.drop_table("equipment")
    op.drop_column("task_instances", "completion_photo_ids")
    op.drop_column("task_instances", "completion_cost")
    op.drop_column("task_instances", "completion_comment")
    op.drop_column("households", "meters_enabled")
