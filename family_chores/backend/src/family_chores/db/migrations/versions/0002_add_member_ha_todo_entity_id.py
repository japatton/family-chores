"""add member.ha_todo_entity_id

Revision ID: 0002_member_ha_todo
Revises: 0001_initial
Create Date: 2026-04-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_member_ha_todo"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("members") as batch:
        batch.add_column(sa.Column("ha_todo_entity_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("members") as batch:
        batch.drop_column("ha_todo_entity_id")
