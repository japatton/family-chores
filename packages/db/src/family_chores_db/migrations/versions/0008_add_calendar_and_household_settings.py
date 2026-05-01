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

  - `household_settings` table — one row per household. Schema:
    synthetic `id INTEGER PRIMARY KEY AUTOINCREMENT` + nullable
    `household_id` (UNIQUE-where-set; NULL for single-tenant addon).
    The synthetic PK is a workaround for SQLAlchemy's identity-map
    rejecting all-NULL primary keys — using `household_id` as the
    sole PK works at the SQL level (SQLite allows NULL in
    single-column PKs) but the ORM refuses to flush such a row.
    Single-row-per-household is enforced application-side by the
    `_load_or_create` get-or-create pattern, not by a UNIQUE
    constraint (SQLite doesn't enforce UNIQUE on NULL columns).
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
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("household_id", sa.String(length=36), nullable=True),
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
    # Index for fast lookup by `household_id` (every read filters on
    # it). Not UNIQUE because SQLite doesn't enforce UNIQUE on NULL,
    # and the application's get-or-create pattern handles
    # single-row-per-household enforcement instead.
    op.create_index(
        "ix_household_settings_household_id",
        "household_settings",
        ["household_id"],
    )


def downgrade() -> None:
    op.drop_table("household_settings")
    # Same rationale as upgrade — `op.drop_column` uses native SQLite
    # ALTER TABLE DROP COLUMN (supported since 3.35 / 2021), avoiding
    # the recreate-table-and-cascade gotcha.
    op.drop_column("members", "calendar_entity_ids")
