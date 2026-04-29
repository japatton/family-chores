"""add reward + redemption tables

Revision ID: 0007_add_rewards
Revises: 0006_add_member_pin_hash
Create Date: 2026-04-29

Rewards catalogue (the second feature from the post-v0.3.1 roadmap-pull).
Two new tables:

  - `reward` — parent-defined catalogue rows (name, cost in points,
    optional weekly cap, optional icon). Soft-delete via `active=False`
    so historical redemptions retain a usable foreign key.
  - `redemption` — kid-initiated request rows. Snapshot fields
    (`reward_name_at_redeem`, `cost_points_at_redeem`) capture what the
    reward looked like at request time; if a parent renames or reprices
    the reward later, historical records stay accurate.

Both tables are tenant-scoped via the standard `household_id` column
pattern.

Points-flow (matches the F-S001 fix from v0.3.1):

  - On request: `MemberStats.points_total -= cost`, `bonus_points_total
    -= cost`. Insufficient balance is a 4xx — points stay where they are.
  - On approve: no points change. Records who approved + when.
  - On deny: `bonus_points_total += cost` (signed, refund). The signed-
    bonus path from F-S001 is what makes this work without a
    "reserved points" mechanism.

Stored as a single FK to `reward` with `ON DELETE RESTRICT` — soft-
delete (active=False) is the supported path; hard-delete is forbidden
to keep audit history intact.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_rewards"
down_revision: str | None = "0006_add_member_pin_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reward",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("household_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cost_points", sa.Integer(), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("max_per_week", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("cost_points > 0", name="ck_reward_cost_positive"),
        sa.CheckConstraint(
            "max_per_week IS NULL OR max_per_week > 0",
            name="ck_reward_max_per_week_positive",
        ),
    )
    op.create_index(
        "ix_reward_household_active",
        "reward",
        ["household_id", "active"],
    )

    op.create_table(
        "redemption",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("household_id", sa.String(length=36), nullable=True),
        sa.Column(
            "reward_id",
            sa.String(length=36),
            sa.ForeignKey("reward.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            sa.Integer(),
            sa.ForeignKey("members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("cost_points_at_redeem", sa.Integer(), nullable=False),
        sa.Column("reward_name_at_redeem", sa.String(length=120), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actor_requested", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("denied_at", sa.DateTime(), nullable=True),
        sa.Column("denied_by", sa.String(length=128), nullable=True),
        sa.Column("denied_reason", sa.String(length=256), nullable=True),
        sa.CheckConstraint(
            "cost_points_at_redeem > 0",
            name="ck_redemption_cost_positive",
        ),
    )
    op.create_index(
        "ix_redemption_household_state",
        "redemption",
        ["household_id", "state"],
    )
    op.create_index(
        "ix_redemption_member",
        "redemption",
        ["member_id", "requested_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_redemption_member", table_name="redemption")
    op.drop_index("ix_redemption_household_state", table_name="redemption")
    op.drop_table("redemption")
    op.drop_index("ix_reward_household_active", table_name="reward")
    op.drop_table("reward")
