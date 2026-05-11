"""add composite (household_id, ts) index on activity_log

Revision ID: 0009_activity_log_index
Revises: 0008_add_calendar
Create Date: 2026-05-02

D-6 from the v0.5.0 ultra-review: `routers/admin.py:list_activity`
filters by `household_id` and orders by `(ts DESC, id DESC)`. The
existing single-column indexes on `activity_log.ts` and `.action`
can't satisfy the ORDER BY when combined with `WHERE household_id`,
so SQLite falls back to a sort. At family scale this is invisible
(tens of rows per day); past tens of thousands of rows (a few months
of heavy use plus the activity logging that landed in v0.4/v0.5) the
sort dominates the query.

Native `op.create_index` only — no table recreate, no cascade risk.
Idempotent: the existing per-column indexes stay (they back other
query shapes like `?action=X`); this is purely additive.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_activity_log_index"
down_revision: str | None = "0008_add_calendar"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_activity_log_household_ts",
        "activity_log",
        ["household_id", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_log_household_ts", table_name="activity_log")
