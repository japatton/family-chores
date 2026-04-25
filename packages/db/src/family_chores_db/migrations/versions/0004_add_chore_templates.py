"""add chore_template + suppression + chore.template_id/ephemeral

Revision ID: 0004_add_chore_templates
Revises: 0003_add_household_id
Create Date: 2026-04-25

Adds the chore-templates feature schema (DECISIONS §13):

  - `chore_template` — reusable blueprints for creating chores. Each row
    carries the parent-facing fields (name, icon, category, points
    suggestion, default recurrence) plus dedup metadata (name_normalized,
    source, starter_key).
  - `household_starter_suppression` — composite-PK table tracking starter
    keys a parent deliberately deleted, so the seeder doesn't re-create
    them on the next startup.
  - Two new columns on `chores`: `template_id` (informational FK back to
    the source template, ON DELETE SET NULL) and `ephemeral` (inverse of
    "save as suggestion" — currently informational, retained for a future
    "save this chore as a suggestion" retrofit).

Existing `chores` rows get `template_id=NULL` and `ephemeral=FALSE` after
the upgrade. No backfill required: `ephemeral=FALSE` is the correct
default for "this chore did not save itself as a suggestion"
(retroactively, none of them did), and a NULL template_id means
"not from a template" which is true for every pre-feature chore.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_chore_templates"
down_revision: str | None = "0003_add_household_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ─── chore_template ───────────────────────────────────────────────
    op.create_table(
        "chore_template",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("household_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("name_normalized", sa.String(length=120), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=32), nullable=True),
        sa.Column("age_min", sa.Integer(), nullable=True),
        sa.Column("age_max", sa.Integer(), nullable=True),
        sa.Column(
            "points_suggested", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("default_recurrence_type", sa.String(length=32), nullable=False),
        sa.Column(
            "default_recurrence_config",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source", sa.String(length=16), nullable=False, server_default="custom"
        ),
        sa.Column("starter_key", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint(
            "household_id", "name_normalized", name="uq_template_household_name"
        ),
        sa.UniqueConstraint(
            "household_id", "starter_key", name="uq_template_household_starter_key"
        ),
        sa.CheckConstraint(
            "points_suggested >= 0", name="ck_template_points_nonneg"
        ),
        sa.CheckConstraint(
            "source IN ('starter', 'custom')", name="ck_template_source_enum"
        ),
    )
    # Per-column indexes mirror what `index=True` on the ORM columns
    # would create. The composite ix_template_household_category covers
    # the common "list this household's templates in category X" query
    # used by the Browse Suggestions panel.
    op.create_index(
        "ix_chore_template_household_id", "chore_template", ["household_id"]
    )
    op.create_index(
        "ix_chore_template_name_normalized", "chore_template", ["name_normalized"]
    )
    op.create_index("ix_chore_template_category", "chore_template", ["category"])
    op.create_index(
        "ix_template_household_category",
        "chore_template",
        ["household_id", "category"],
    )

    # ─── household_starter_suppression ────────────────────────────────
    # Composite PK on (household_id, starter_key). SQLite permits NULL in
    # composite PK columns — single-tenant addon mode uses NULL
    # household_id, same convention as the rest of the schema.
    op.create_table(
        "household_starter_suppression",
        sa.Column("household_id", sa.String(length=36), nullable=True),
        sa.Column("starter_key", sa.String(length=64), nullable=False),
        sa.Column(
            "suppressed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.PrimaryKeyConstraint(
            "household_id", "starter_key", name="pk_household_starter_suppression"
        ),
    )

    # ─── chores additions ─────────────────────────────────────────────
    # Alembic's batch mode rebuilds the table on SQLite; it requires every
    # constraint (including inline FKs) to have an explicit name so it
    # can re-create them in the rebuilt table. Without `name=...` here,
    # batch mode raises `ValueError: Constraint must have a name`.
    with op.batch_alter_table("chores") as batch:
        batch.add_column(
            sa.Column(
                "template_id",
                sa.String(length=36),
                sa.ForeignKey(
                    "chore_template.id",
                    ondelete="SET NULL",
                    name="fk_chores_template_id",
                ),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "ephemeral",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    op.create_index("ix_chores_template_id", "chores", ["template_id"])


def downgrade() -> None:
    # Reverse order — chore.template_id has a FK into chore_template, so
    # drop the column first, then the templates table.
    op.drop_index("ix_chores_template_id", table_name="chores")
    with op.batch_alter_table("chores") as batch:
        batch.drop_column("ephemeral")
        batch.drop_column("template_id")

    op.drop_table("household_starter_suppression")

    op.drop_index("ix_template_household_category", table_name="chore_template")
    op.drop_index("ix_chore_template_category", table_name="chore_template")
    op.drop_index("ix_chore_template_name_normalized", table_name="chore_template")
    op.drop_index("ix_chore_template_household_id", table_name="chore_template")
    op.drop_table("chore_template")
