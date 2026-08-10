"""Add private files, verified archives and restore reports.

Revision ID: 0009_files_backups_transfer
Revises: 0008_realtime_offline_conflicts
Create Date: 2026-08-01 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_files_backups_transfer"
down_revision: str | None = "0008_realtime_offline_conflicts"
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
        "file_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("uploaded_by_id", sa.String(36), nullable=True),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("original_mime", sa.String(80), nullable=False),
        sa.Column("stored_mime", sa.String(80), nullable=False),
        sa.Column("stored_path", sa.String(500), nullable=False, unique=True),
        sa.Column("thumbnail_path", sa.String(500), nullable=True, unique=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in (
        "household_id",
        "uploaded_by_id",
        "entity_type",
        "entity_id",
        "purpose",
        "checksum",
        "deleted_at",
    ):
        op.create_index(f"ix_file_assets_{column}", "file_assets", [column])

    op.create_table(
        "backup_archives",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("created_by_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("app_version", sa.String(24), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("kind", "path"),
    )
    for column in ("household_id", "created_by_id", "kind", "status"):
        op.create_index(f"ix_backup_archives_{column}", "backup_archives", [column])

    op.create_table(
        "restore_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("performed_by_id", sa.String(36), nullable=True),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("counts_before", sa.JSON(), nullable=False),
        sa.Column("counts_after", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["performed_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_restore_reports_household_id", "restore_reports", ["household_id"])
    op.create_index("ix_restore_reports_performed_by_id", "restore_reports", ["performed_by_id"])


def downgrade() -> None:
    op.drop_table("restore_reports")
    op.drop_table("backup_archives")
    op.drop_table("file_assets")
