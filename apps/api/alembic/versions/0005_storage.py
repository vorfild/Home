"""Add storage tree, inventory items, stable QR and review timers.

Revision ID: 0005_storage
Revises: 0004_shopping
Create Date: 2026-08-01 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_storage"
down_revision: str | None = "0004_shopping"
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
    op.add_column("task_definitions", sa.Column("source_type", sa.String(length=40), nullable=True))
    op.add_column("task_definitions", sa.Column("source_id", sa.String(length=36), nullable=True))
    op.create_index("ix_task_definitions_source_type", "task_definitions", ["source_type"])
    op.create_index("ix_task_definitions_source_id", "task_definitions", ["source_id"])
    op.create_index(
        "uq_task_definitions_source",
        "task_definitions",
        ["source_type", "source_id"],
        unique=True,
    )
    op.create_table(
        "storage_nodes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("node_type", sa.String(length=40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("qr_token", sa.String(length=64), nullable=True),
        sa.Column("qr_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["storage_nodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("qr_token"),
    )
    op.create_index("ix_storage_nodes_household_id", "storage_nodes", ["household_id"])
    op.create_index("ix_storage_nodes_parent_id", "storage_nodes", ["parent_id"])
    op.create_index("ix_storage_nodes_qr_token", "storage_nodes", ["qr_token"], unique=True)
    op.create_index("ix_storage_nodes_deleted_at", "storage_nodes", ["deleted_at"])
    op.create_index("ix_storage_nodes_purge_after", "storage_nodes", ["purge_after"])
    op.create_table(
        "storage_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("normalized_name", sa.String(length=180), nullable=False),
        sa.Column("photo_ids", sa.JSON(), nullable=False),
        sa.Column("primary_photo_id", sa.String(length=36), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=True),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("item_status", sa.String(length=24), nullable=False),
        sa.Column("placed_at", sa.Date(), nullable=True),
        sa.Column("location_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.Date(), nullable=True),
        sa.Column("value", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("purchased_on", sa.Date(), nullable=True),
        sa.Column("manufacturer", sa.String(length=120), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("serial_number", sa.String(length=160), nullable=True),
        sa.Column("warranty_until", sa.Date(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["storage_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "household_id",
        "node_id",
        "name",
        "normalized_name",
        "category",
        "owner_id",
        "item_status",
        "serial_number",
        "review_at",
        "review_status",
        "archived_at",
    ):
        op.create_index(f"ix_storage_items_{column}", "storage_items", [column])


def downgrade() -> None:
    op.drop_table("storage_items")
    op.drop_table("storage_nodes")
    op.drop_index("uq_task_definitions_source", table_name="task_definitions")
    op.drop_index("ix_task_definitions_source_id", table_name="task_definitions")
    op.drop_index("ix_task_definitions_source_type", table_name="task_definitions")
    op.drop_column("task_definitions", "source_id")
    op.drop_column("task_definitions", "source_type")
