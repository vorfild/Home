"""Add shopping lists, items, proposals and offline operation keys.

Revision ID: 0004_shopping
Revises: 0003_tasks_and_today
Create Date: 2026-08-01 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_shopping"
down_revision: str | None = "0003_tasks_and_today"
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
    op.create_table(
        "shopping_lists",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("store", sa.String(length=120), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responsible_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shopping_lists_household_id", "shopping_lists", ["household_id"])
    op.create_index("ix_shopping_lists_store", "shopping_lists", ["store"])
    op.create_index("ix_shopping_lists_scheduled_at", "shopping_lists", ["scheduled_at"])
    op.create_index("ix_shopping_lists_responsible_id", "shopping_lists", ["responsible_id"])
    op.create_index("ix_shopping_lists_status", "shopping_lists", ["status"])
    op.create_table(
        "shopping_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("normalized_name", sa.String(length=180), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("added_by_id", sa.String(length=36), nullable=True),
        sa.Column("recipient_id", sa.String(length=36), nullable=True),
        sa.Column("purchased", sa.Boolean(), nullable=False),
        sa.Column("photo_id", sa.String(length=36), nullable=True),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("store", sa.String(length=120), nullable=True),
        sa.Column("proposal_status", sa.String(length=12), nullable=False),
        sa.Column("decided_by_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_operation_id", sa.String(length=64), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["added_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["list_id"], ["shopping_lists.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["recipient_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_operation_id"),
    )
    op.create_index("ix_shopping_items_list_id", "shopping_items", ["list_id"])
    op.create_index("ix_shopping_items_name", "shopping_items", ["name"])
    op.create_index("ix_shopping_items_normalized_name", "shopping_items", ["normalized_name"])
    op.create_index("ix_shopping_items_category", "shopping_items", ["category"])
    op.create_index("ix_shopping_items_recipient_id", "shopping_items", ["recipient_id"])
    op.create_index("ix_shopping_items_proposal_status", "shopping_items", ["proposal_status"])
    op.create_index(
        "ix_shopping_items_client_operation_id",
        "shopping_items",
        ["client_operation_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("shopping_items")
    op.drop_table("shopping_lists")
