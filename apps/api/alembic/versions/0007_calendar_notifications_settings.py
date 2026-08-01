"""Add calendar preferences, notifications, push subscriptions and module settings.

Revision ID: 0007_calendar_notifications_settings
Revises: 0006_home
Create Date: 2026-08-01 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_calendar_notifications_settings"
down_revision: str | None = "0006_home"
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
        sa.Column(
            "module_settings",
            sa.JSON(),
            server_default=sa.text(
                '\'{"meters": true, "email": false, "shopping_prices": true, '
                '"maintenance_finances": true, "task_photos": true}\''
            ),
            nullable=False,
        ),
    )
    op.add_column(
        "households",
        sa.Column("server_settings", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("event_rules", sa.JSON(), nullable=False),
        sa.Column("reminder_minutes", sa.Integer(), nullable=False),
        sa.Column("repeat_minutes", sa.Integer(), nullable=True),
        sa.Column("quiet_start", sa.Time(), nullable=True),
        sa.Column("quiet_end", sa.Time(), nullable=True),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("theme", sa.String(16), nullable=False),
        sa.Column("font_scale", sa.String(16), nullable=False),
        sa.Column("density", sa.String(16), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True)
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("household_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=True),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("dedupe_key", sa.String(220), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("push_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_error", sa.String(300), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("dedupe_key"),
    )
    for column in (
        "household_id",
        "user_id",
        "event_type",
        "source_type",
        "source_id",
        "read_at",
    ):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    op.drop_table("notifications")
    op.drop_table("user_preferences")
    op.drop_column("households", "server_settings")
    op.drop_column("households", "module_settings")
