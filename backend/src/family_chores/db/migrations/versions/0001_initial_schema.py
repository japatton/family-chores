"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("avatar", sa.String(length=256), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=False),
        sa.Column("display_mode", sa.String(length=16), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("slug", name="uq_members_slug"),
    )

    op.create_table(
        "chores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image", sa.String(length=256), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("recurrence_type", sa.String(length=32), nullable=False),
        sa.Column("recurrence_config", sa.JSON(), nullable=False),
        sa.Column("time_window_start", sa.Time(), nullable=True),
        sa.Column("time_window_end", sa.Time(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("points >= 0", name="ck_chores_points_nonneg"),
    )
    op.create_index("ix_chores_active", "chores", ["active"])

    op.create_table(
        "chore_assignments",
        sa.Column("chore_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chore_id"], ["chores.id"], name="fk_chore_assignments_chore_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name="fk_chore_assignments_member_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("chore_id", "member_id"),
    )

    op.create_table(
        "chore_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chore_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("points_awarded", sa.Integer(), nullable=False),
        sa.Column("ha_todo_uid", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["chore_id"], ["chores.id"], name="fk_chore_instances_chore_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name="fk_chore_instances_member_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint("points_awarded >= 0", name="ck_chore_instances_points_nonneg"),
        sa.UniqueConstraint("chore_id", "member_id", "date", name="uq_chore_instances_cmd"),
    )
    op.create_index("ix_chore_instances_chore_id", "chore_instances", ["chore_id"])
    op.create_index("ix_chore_instances_member_id", "chore_instances", ["member_id"])
    op.create_index("ix_chore_instances_date", "chore_instances", ["date"])
    op.create_index("ix_chore_instances_state", "chore_instances", ["state"])
    op.create_index("ix_chore_instances_member_date", "chore_instances", ["member_id", "date"])

    op.create_table(
        "member_stats",
        sa.Column("member_id", sa.Integer(), primary_key=True),
        sa.Column("points_total", sa.Integer(), nullable=False),
        sa.Column("points_this_week", sa.Integer(), nullable=False),
        sa.Column("week_anchor", sa.Date(), nullable=True),
        sa.Column("streak", sa.Integer(), nullable=False),
        sa.Column("last_all_done_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["member_id"], ["members.id"], name="fk_member_stats_member_id", ondelete="CASCADE"
        ),
        sa.CheckConstraint("points_total >= 0", name="ck_member_stats_total_nonneg"),
        sa.CheckConstraint("points_this_week >= 0", name="ck_member_stats_week_nonneg"),
        sa.CheckConstraint("streak >= 0", name="ck_member_stats_streak_nonneg"),
    )

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_activity_log_ts", "activity_log", ["ts"])
    op.create_index("ix_activity_log_action", "activity_log", ["action"])

    op.create_table(
        "app_config",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("app_config")
    op.drop_index("ix_activity_log_action", table_name="activity_log")
    op.drop_index("ix_activity_log_ts", table_name="activity_log")
    op.drop_table("activity_log")
    op.drop_table("member_stats")
    op.drop_index("ix_chore_instances_member_date", table_name="chore_instances")
    op.drop_index("ix_chore_instances_state", table_name="chore_instances")
    op.drop_index("ix_chore_instances_date", table_name="chore_instances")
    op.drop_index("ix_chore_instances_member_id", table_name="chore_instances")
    op.drop_index("ix_chore_instances_chore_id", table_name="chore_instances")
    op.drop_table("chore_instances")
    op.drop_table("chore_assignments")
    op.drop_index("ix_chores_active", table_name="chores")
    op.drop_table("chores")
    op.drop_table("members")
