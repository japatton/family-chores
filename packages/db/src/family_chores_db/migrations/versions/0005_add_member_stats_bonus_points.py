"""add member_stats.bonus_points_total

Revision ID: 0005_add_bonus_points
Revises: 0004_add_chore_templates
Create Date: 2026-04-25

Fix for the F-S001 finding: manual point adjustments via
`adjust_member_points` were silently wiped at the next midnight rollover
because `recompute_stats_for_member` overwrote `points_total` with a
fresh sum of `chore_instances.points_awarded` only.

This migration adds a `bonus_points_total INTEGER NOT NULL DEFAULT 0`
column to `member_stats`. The column accumulates parent-applied
adjustments (positive or negative — no check constraint) and the recompute
path now does:

    stats.points_total = max(0, sum(chore_instances.points_awarded)
                                  + stats.bonus_points_total)

so the adjustment survives recompute. The outer max(0, ...) preserves the
existing "displayed total can never go negative" semantic.

Existing rows pick up `bonus_points_total = 0` via `server_default`. No
backfill needed: parents who'd previously had adjustments wiped will see
0 from the new column. They can re-apply the lost adjustment if they
remember it.

Behavior change worth noting (commit body has more):

  Before: adjusting -100 against a 10-point member showed 0 forever; the
  -90 was discarded.
  After:  adjusting -100 against a 10-point member shows 0 immediately,
  bonus_points_total holds -90, and the kid's next 90 points of
  chore-derived points are absorbed by the deficit (the kid is "in debt"
  until they earn back through). This matches a real-world penalty
  semantic; the "discard the rest" semantic was an artefact of
  per-call clamping.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_bonus_points"
down_revision: str | None = "0004_add_chore_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("member_stats") as batch:
        batch.add_column(
            sa.Column(
                "bonus_points_total",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("member_stats") as batch:
        batch.drop_column("bonus_points_total")
