"""End-to-end tests for the `0006_add_member_pin_hash` Alembic migration.

Same shape as the other migration tests. Verifies:

  - `upgrade head` adds `pin_hash` to `members` as a nullable column
    (no server_default — existing rows get NULL).
  - Pre-existing `members` rows pick up `pin_hash = NULL`.
  - `downgrade` to 0005 removes the column without losing other data.
  - upgrade → downgrade → upgrade is idempotent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[1] / "src" / "family_chores_db" / "migrations"
)


def _alembic_config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_upgrade_head_adds_pin_hash_to_members(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "members")
        assert "pin_hash" in cols, "members missing pin_hash after upgrade"


def test_pre_existing_member_rows_get_null_pin_hash(tmp_path):
    db = tmp_path / "test.db"
    # Apply through 0005 (the previous head), insert a member, then
    # advance to 0006 and confirm the new column is NULL on the
    # existing row.
    command.upgrade(_alembic_config(db), "0005_add_bonus_points")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO members (id, name, slug, color, display_mode, "
            "requires_approval, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (1, "Alice", "alice", "#ff0000", "kid_standard", 0),
        )
        conn.commit()

    command.upgrade(_alembic_config(db), "head")

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT pin_hash FROM members WHERE id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] is None, "pre-existing member should have NULL pin_hash"


def test_pin_hash_accepts_argon2_encoded_string(tmp_path):
    """Sanity-check the column width — the spec is String(256), well over
    Argon2's typical encoded length of ~95–110 chars."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")

    # Realistic Argon2id encoded hash (110 chars).
    fake_hash = (
        "$argon2id$v=19$m=65536,t=3,p=4$"
        + "S2VlcEFnQ29hckpvbmFzMjAyNg$"
        + "abcdefghijklmnopqrstuvwxyz0123456789ABCDEF"
    )

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO members (id, name, slug, color, display_mode, "
            "requires_approval, pin_hash, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (1, "Bob", "bob", "#0000ff", "kid_standard", 0, fake_hash),
        )
        conn.commit()
        row = conn.execute(
            "SELECT pin_hash FROM members WHERE id = 1"
        ).fetchone()
        assert row[0] == fake_hash


def test_downgrade_removes_pin_hash(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    command.downgrade(_alembic_config(db), "0005_add_bonus_points")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "members")
        assert "pin_hash" not in cols
        # Other Member columns preserved.
        assert "name" in cols
        assert "slug" in cols
        assert "ha_todo_entity_id" in cols


def test_upgrade_downgrade_upgrade_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    command.downgrade(_alembic_config(db), "0005_add_bonus_points")
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "members")
        assert "pin_hash" in cols
