"""End-to-end tests for the `0005_add_bonus_points` Alembic migration.

Same shape as `test_migration_0004.py` — invokes Alembic against a real
SQLite file. Verifies:

  - `upgrade head` adds `bonus_points_total` to `member_stats` with a
    server_default of 0.
  - Pre-existing `member_stats` rows pick up `bonus_points_total = 0`.
  - The column accepts negative values (no `>= 0` check constraint;
    the F-S001 fix relies on signed bonuses).
  - `downgrade -1` removes the column without touching other data.
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


def test_upgrade_head_adds_bonus_points_total_to_member_stats(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "member_stats")
        assert "bonus_points_total" in cols, (
            "member_stats missing bonus_points_total after `upgrade head`"
        )


def test_pre_existing_rows_get_bonus_points_zero(tmp_path):
    """Apply 0001-0004, insert a member + stats row, then upgrade to 0005."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "0004_add_chore_templates")
    with sqlite3.connect(db) as conn:
        # Minimum-viable rows to satisfy the FK on member_stats.
        conn.execute(
            "INSERT INTO members (id, name, slug, color, display_mode, "
            "requires_approval, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (1, "Alice", "alice", "#ff0000", "kid_standard", 0),
        )
        conn.execute(
            "INSERT INTO member_stats (member_id, points_total, "
            "points_this_week, streak, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (1, 42, 7, 3),
        )
        conn.commit()

    command.upgrade(_alembic_config(db), "head")

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT points_total, bonus_points_total FROM member_stats "
            "WHERE member_id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == 42, "existing points_total preserved"
        assert row[1] == 0, "new bonus_points_total defaults to 0 for old rows"


def test_bonus_points_total_accepts_negative_values(tmp_path):
    """Signed semantic — F-S001 fix uses negative bonus to represent debt."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO members (id, name, slug, color, display_mode, "
            "requires_approval, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (1, "Bob", "bob", "#0000ff", "kid_standard", 0),
        )
        conn.execute(
            "INSERT INTO member_stats (member_id, points_total, "
            "points_this_week, streak, bonus_points_total, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (1, 0, 0, 0, -50),
        )
        conn.commit()
        row = conn.execute(
            "SELECT bonus_points_total FROM member_stats WHERE member_id = 1"
        ).fetchone()
        assert row[0] == -50


def test_downgrade_removes_bonus_points_total(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "0005_add_bonus_points")
    command.downgrade(_alembic_config(db), "0004_add_chore_templates")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "member_stats")
        assert "bonus_points_total" not in cols
        # Existing schema preserved.
        assert "points_total" in cols
        assert "points_this_week" in cols


def test_upgrade_downgrade_upgrade_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    # Pin the test to 0005 specifically — `head` advances as new migrations
    # land (0006 added pin_hash on members), so `-1` would no longer roll
    # back the bonus_points_total change without a migration-target.
    command.upgrade(_alembic_config(db), "0005_add_bonus_points")
    command.downgrade(_alembic_config(db), "0004_add_chore_templates")
    command.upgrade(_alembic_config(db), "0005_add_bonus_points")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "member_stats")
        assert "bonus_points_total" in cols
