"""Add durable realtime events, entity versions, offline operations and conflicts.

Revision ID: 0008_realtime_offline_conflicts
Revises: 0007_calendar_notifications_settings
Create Date: 2026-08-01 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_realtime_offline_conflicts"
down_revision: str | None = "0007_calendar_notifications_settings"
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
        "task_instances", sa.Column("completion_operation_id", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_task_instances_completion_operation_id",
        "task_instances",
        ["completion_operation_id"],
        unique=True,
    )
    op.create_table(
        "sync_events",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(120), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ("household_id", "entity_type", "entity_id", "actor_id", "created_at"):
        op.create_index(f"ix_sync_events_{column}", "sync_events", [column])
    op.create_table(
        "entity_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("field_versions", sa.JSON(), nullable=False),
        sa.Column("last_actor_id", sa.String(36), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("household_id", "entity_type", "entity_id"),
    )
    for column in ("household_id", "entity_type", "entity_id"):
        op.create_index(f"ix_entity_versions_{column}", "entity_versions", [column])
    op.create_table(
        "sync_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_operation_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("result_status", sa.String(24), nullable=False),
        sa.Column("result_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("client_operation_id"),
    )
    op.create_index(
        "ix_sync_operations_client_operation_id",
        "sync_operations",
        ["client_operation_id"],
        unique=True,
    )
    op.create_index("ix_sync_operations_user_id", "sync_operations", ["user_id"])
    op.create_table(
        "sync_conflicts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("field_name", sa.String(80), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("server_version", sa.Integer(), nullable=False),
        sa.Column("server_value", sa.JSON(), nullable=True),
        sa.Column("alternative_value", sa.JSON(), nullable=True),
        sa.Column("proposed_by_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("resolved_by_id", sa.String(36), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("manual_value", sa.JSON(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proposed_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in (
        "household_id",
        "entity_type",
        "entity_id",
        "field_name",
        "proposed_by_id",
        "status",
    ):
        op.create_index(f"ix_sync_conflicts_{column}", "sync_conflicts", [column])


def downgrade() -> None:
    op.drop_table("sync_conflicts")
    op.drop_table("sync_operations")
    op.drop_table("entity_versions")
    op.drop_table("sync_events")
    op.drop_index("ix_task_instances_completion_operation_id", table_name="task_instances")
    op.drop_column("task_instances", "completion_operation_id")
