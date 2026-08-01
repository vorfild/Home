"""Add household, users, sessions, trusted devices and absences.

Revision ID: 0002_identity_and_family
Revises: 0001_project_foundation
Create Date: 2026-08-01 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_identity_and_family"
down_revision: str | None = "0001_project_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> tuple[sa.Column[sa.DateTime], sa.Column[sa.DateTime]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("singleton_key", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("notification_settings", sa.JSON(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("singleton_key = 1", name=op.f("ck_households_household_singleton")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_households")),
        sa.UniqueConstraint("singleton_key", name=op.f("uq_households_singleton_key")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("login", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("pin_hash", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("avatar_path", sa.String(length=500), nullable=True),
        sa.Column("password_change_required", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("role IN ('admin', 'adult', 'child')", name=op.f("ck_users_user_role")),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_users_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("login", name=op.f("uq_users_login")),
    )
    op.create_index(op.f("ix_users_household_id"), "users", ["household_id"])
    op.create_index(op.f("ix_users_login"), "users", ["login"], unique=True)
    op.create_table(
        "trusted_devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_trusted_devices_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trusted_devices")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_trusted_devices_token_hash")),
    )
    op.create_index(op.f("ix_trusted_devices_household_id"), "trusted_devices", ["household_id"])
    op.create_index(
        op.f("ix_trusted_devices_token_hash"), "trusted_devices", ["token_hash"], unique=True
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trusted_device_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["trusted_device_id"],
            ["trusted_devices.id"],
            name=op.f("fk_sessions_trusted_device_id_trusted_devices"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"])
    op.create_index(op.f("ix_sessions_token_hash"), "sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"])
    op.create_table(
        "absences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("substitute_user_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.String(length=300), nullable=True),
        *timestamps(),
        sa.CheckConstraint("ends_on >= starts_on", name=op.f("ck_absences_absence_date_order")),
        sa.ForeignKeyConstraint(
            ["substitute_user_id"],
            ["users.id"],
            name=op.f("fk_absences_substitute_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_absences_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_absences")),
    )
    op.create_index(op.f("ix_absences_user_id"), "absences", ["user_id"])
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("login", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index(op.f("ix_login_attempts_attempted_at"), "login_attempts", ["attempted_at"])
    op.create_index(op.f("ix_login_attempts_ip_address"), "login_attempts", ["ip_address"])
    op.create_index(op.f("ix_login_attempts_login"), "login_attempts", ["login"])


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_table("absences")
    op.drop_table("sessions")
    op.drop_table("trusted_devices")
    op.drop_table("users")
    op.drop_table("households")
