"""Add rooms, categories, trash and repair archive state.

Revision ID: 0010_lifecycle_catalogs
Revises: 0009_files_backups_transfer
Create Date: 2026-08-01 23:00:00
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0010_lifecycle_catalogs"
down_revision: str | None = "0009_files_backups_transfer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULTS = {
    "task": ["уборка", "готовка", "стирка", "питомцы", "обслуживание", "другое"],
    "shopping": ["продукты", "хозяйственное", "аптека", "одежда", "другое"],
    "storage": [
        "одежда",
        "инструменты",
        "техника",
        "туризм и поездки",
        "документы",
        "сезонное",
        "другое",
    ],
}


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
        "maintenance_records", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_maintenance_records_archived_at", "maintenance_records", ["archived_at"])
    op.create_table(
        "rooms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("household_id", "name"),
    )
    op.create_index("ix_rooms_household_id", "rooms", ["household_id"])
    op.create_index("ix_rooms_is_active", "rooms", ["is_active"])
    op.create_table(
        "categories",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("domain", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(7), nullable=False),
        sa.Column("icon", sa.String(40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("household_id", "domain", "name"),
    )
    for column in ("household_id", "domain", "is_active"):
        op.create_index(f"ix_categories_{column}", "categories", [column])
    op.create_table(
        "trash_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("deleted_by_id", sa.String(36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_action", sa.String(16), nullable=False),
        sa.Column("previous_state", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("household_id", "entity_type", "entity_id"),
    )
    for column in (
        "household_id",
        "entity_type",
        "entity_id",
        "deleted_by_id",
        "deleted_at",
        "purge_after",
    ):
        op.create_index(f"ix_trash_entries_{column}", "trash_entries", [column])

    connection = op.get_bind()
    households = [row[0] for row in connection.execute(sa.text("SELECT id FROM households"))]
    category_table = sa.table(
        "categories",
        sa.column("id", sa.String),
        sa.column("household_id", sa.String),
        sa.column("domain", sa.String),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("color", sa.String),
        sa.column("icon", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("is_default", sa.Boolean),
    )
    rows = [
        {
            "id": str(uuid4()),
            "household_id": household_id,
            "domain": domain,
            "name": name,
            "sort_order": position,
            "color": "#5E7FA3",
            "icon": "tag",
            "is_active": True,
            "is_default": True,
        }
        for household_id in households
        for domain, names in DEFAULTS.items()
        for position, name in enumerate(names)
    ]
    if rows:
        op.bulk_insert(category_table, rows)


def downgrade() -> None:
    op.drop_table("trash_entries")
    op.drop_table("categories")
    op.drop_table("rooms")
    op.drop_index("ix_maintenance_records_archived_at", table_name="maintenance_records")
    op.drop_column("maintenance_records", "archived_at")
