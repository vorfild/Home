"""Add task definitions, calendar instances, queues and history.

Revision ID: 0003_tasks_and_today
Revises: 0002_identity_and_family
Create Date: 2026-08-01 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_tasks_and_today"
down_revision: str | None = "0002_identity_and_family"
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
        "task_definitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("household_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("room", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("priority", sa.String(length=12), nullable=False),
        sa.Column("assignment_mode", sa.String(length=12), nullable=False),
        sa.Column("repeat_rule", sa.JSON(), nullable=False),
        sa.Column("reminders", sa.JSON(), nullable=False),
        sa.Column("requires_photo", sa.Boolean(), nullable=False),
        sa.Column("requires_adult_review", sa.Boolean(), nullable=False),
        sa.Column("current_queue_index", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_definitions_household_id", "task_definitions", ["household_id"])
    op.create_index("ix_task_definitions_room", "task_definitions", ["room"])
    op.create_index("ix_task_definitions_category", "task_definitions", ["category"])
    op.create_index("ix_task_definitions_priority", "task_definitions", ["priority"])
    op.create_table(
        "task_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "user_id"),
    )
    op.create_index("ix_task_assignments_task_id", "task_assignments", ["task_id"])
    op.create_index("ix_task_assignments_user_id", "task_assignments", ["user_id"])
    op.create_table(
        "task_queue_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "position"),
        sa.UniqueConstraint("task_id", "user_id"),
    )
    op.create_index("ix_task_queue_members_task_id", "task_queue_members", ["task_id"])
    op.create_index("ix_task_queue_members_user_id", "task_queue_members", ["user_id"])
    op.create_table(
        "task_subtasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_subtasks_task_id", "task_subtasks", ["task_id"])
    op.create_table(
        "task_instances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assignee_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("completed_by_id", sa.String(length=36), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_photo_id", sa.String(length=36), nullable=True),
        sa.Column("review_comment", sa.String(length=500), nullable=True),
        sa.Column("subtask_state", sa.JSON(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["completed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["task_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "sequence"),
    )
    op.create_index("ix_task_instances_task_id", "task_instances", ["task_id"])
    op.create_index("ix_task_instances_due_at", "task_instances", ["due_at"])
    op.create_index("ix_task_instances_assignee_id", "task_instances", ["assignee_id"])
    op.create_index("ix_task_instances_status", "task_instances", ["status"])
    op.create_table(
        "task_history",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("instance_id", sa.String(length=36), nullable=True),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["instance_id"], ["task_instances.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["task_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_history_task_id", "task_history", ["task_id"])
    op.create_index("ix_task_history_instance_id", "task_history", ["instance_id"])
    op.create_index("ix_task_history_happened_at", "task_history", ["happened_at"])


def downgrade() -> None:
    op.drop_table("task_history")
    op.drop_table("task_instances")
    op.drop_table("task_subtasks")
    op.drop_table("task_queue_members")
    op.drop_table("task_assignments")
    op.drop_table("task_definitions")
