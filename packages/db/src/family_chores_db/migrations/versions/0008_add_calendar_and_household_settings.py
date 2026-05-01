"""add members.calendar_entity_ids + household_settings table

Revision ID: 0008_add_calendar
Revises: 0007_add_rewards
Create Date: 2026-04-30

Schema for the calendar-integration feature (DECISIONS §14). Two
changes:

  - `members.calendar_entity_ids: JSON` — list of HA `calendar.*`
    entity IDs the parent has assigned to this member. Defaults to
    empty list for existing rows. Single column; the addon parses it
    as `list[str]` via the ORM's JSON binding. Per-member calendar
    privacy lives here — events on Mom's work calendar simply aren't
    mapped to anyone.

  - `household_settings` table — single row per household, scoped via
    the standard `household_id` pattern. Holds the
    `shared_calendar_entity_ids` JSON list plus reserved space for
    future household-level config (the existing `app_config` bag was
    deliberately not extended; a real table is cleaner long-term).

The `household_id` column on the new table follows the same NULL-in-
single-tenant convention as the rest of the codebase. Single PK on
`household_id` so a household can't have two settings rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_add_calendar"
down_revision: str | None = "0007_add_rewards"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── members.calendar_entity_ids ──────────────────────────────────
    # JSON column, defaults to '[]' so existing rows pick up an empty
    # list. SQLAlchemy's JSON type maps to TEXT in SQLite; the
    # server_default literal must be the JSON-encoded value.
    #
    # Using native `op.add_column` rather than `op.batch_alter_table`
    # here is deliberate: batch_alter_table recreates the entire SQLite
    # table when adding a NOT NULL column, which fires `ON DELETE
    # CASCADE` on every FK pointing at it — silently wiping
    # member_stats / chore_assignments / chore_instances / etc. SQLite
    # supports native ADD COLUMN with a non-NULL default, so we use
    # that path. (Migration 0006 used batch_alter for the nullable
    # `pin_hash` column, which doesn't trigger the recreate.)
    op.add_column(
        "members",
        sa.Column(
            "calendar_entity_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    # ─── household_settings ───────────────────────────────────────────
    op.create_table(
        "household_settings",
        sa.Column("household_id", sa.String(length=36), primary_key=True, nullable=True),
        sa.Column(
            "shared_calendar_entity_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
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
    )


def downgrade() -> None:
    op.drop_table("household_settings")
    # Same rationale as upgrade — `op.drop_column` uses native SQLite
    # ALTER TABLE DROP COLUMN (supported since 3.35 / 2021), avoiding
    # the recreate-table-and-cascade gotcha.
    op.drop_column("members", "calendar_entity_ids")
