"""add household_id to every tenant-scoped table

Revision ID: 0003_add_household_id
Revises: 0002_member_ha_todo
Create Date: 2026-04-23

Adds a nullable `household_id VARCHAR(36)` column + index to every table
the service layer scopes by tenant: `members`, `chores`,
`chore_assignments`, `chore_instances`, `member_stats`, `activity_log`,
`app_config`. See DECISIONS §11 step 8.

This migration is **deliberately a no-op for existing data**:

  - No backfill — all existing rows get NULL.
  - No NOT NULL constraint — single-tenant add-on mode keeps writing
    NULL; the service-layer `scoped()` helper (step 9) treats NULL as
    "no household filter" so query results are byte-identical to the
    pre-migration behavior.
  - The future SaaS deployment (Phase 3) will land a separate migration
    that flips this column to NOT NULL once every row has been
    backfilled with a real household.

Index on every column. SaaS-side queries WILL filter by household_id on
every table, so the index pays for itself there; on the add-on it costs
a few KB of B-tree per table for nothing — acceptable.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_add_household_id"
down_revision: str | None = "0002_member_ha_todo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables the service layer scopes by tenant. Order doesn't matter for
# correctness; kept stable so migration logs are deterministic.
_SCOPED_TABLES: tuple[str, ...] = (
    "members",
    "chores",
    "chore_assignments",
    "chore_instances",
    "member_stats",
    "activity_log",
    "app_config",
)


def upgrade() -> None:
    for table in _SCOPED_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("household_id", sa.String(length=36), nullable=True))
        op.create_index(f"ix_{table}_household_id", table, ["household_id"])


def downgrade() -> None:
    # Reverse order — drop indexes before dropping columns. SQLite handles
    # both via batch but being explicit makes the intent obvious.
    for table in reversed(_SCOPED_TABLES):
        op.drop_index(f"ix_{table}_household_id", table_name=table)
        with op.batch_alter_table(table) as batch:
            batch.drop_column("household_id")
