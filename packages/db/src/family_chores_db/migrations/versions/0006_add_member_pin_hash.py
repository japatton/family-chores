"""add member.pin_hash for the per-kid soft lock

Revision ID: 0006_add_member_pin_hash
Revises: 0005_add_bonus_points
Create Date: 2026-04-29

Adds an optional per-member soft-lock PIN. Same threat model as the
parent PIN (DECISIONS §4 #34): a convenience gate that stops siblings
from tapping each other's chores on the wall-mounted tablet, NOT a
security boundary. The hash is Argon2 (reuses the existing
`hash_pin`/`verify_pin` helpers in `packages/api/.../security.py`).

`pin_hash` is `String(256)` to give Argon2 plenty of room (typical
encoded length is ~95–110 chars; the column has slack for future
parameter changes). Nullable — most members won't have a PIN.

No backfill: existing members get NULL, which the API surfaces as
`pin_set: false`. Setting / clearing happens via the new
`/api/members/{slug}/pin/{set,verify,clear}` endpoints.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_member_pin_hash"
down_revision: str | None = "0005_add_bonus_points"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("members") as batch:
        batch.add_column(
            sa.Column("pin_hash", sa.String(length=256), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("members") as batch:
        batch.drop_column("pin_hash")
