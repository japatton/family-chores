"""End-to-end tests for the `0008_add_calendar` Alembic migration.

Same shape as the other migration tests. Covers:

  - `upgrade head` adds `members.calendar_entity_ids` (JSON, NOT NULL,
    server_default '[]') and creates `household_settings` table.
  - Pre-existing `members` rows pick up `calendar_entity_ids = '[]'`
    via the server_default — verifies the FK-cascade-on-batch-alter
    bug noted in the migration's docstring is actually avoided.
  - `household_settings` accepts the standard NULL household_id PK.
  - `downgrade` to 0007 cleanly removes both schema additions.
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


def _seed_member(conn: sqlite3.Connection, member_id: int = 1) -> None:
    conn.execute(
        "INSERT INTO members (id, name, slug, color, display_mode, "
        "requires_approval, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (member_id, "Alice", f"alice{member_id}", "#ff0000", "kid_standard", 0),
    )


def test_upgrade_head_adds_calendar_entity_ids(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "members")
        assert "calendar_entity_ids" in cols


def test_upgrade_head_creates_household_settings(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "household_settings" in tables
        cols = _columns(conn, "household_settings")
        for col in (
            "household_id",
            "shared_calendar_entity_ids",
            "created_at",
            "updated_at",
        ):
            assert col in cols, f"household_settings missing {col}"


def test_existing_member_rows_get_empty_calendar_list(tmp_path):
    """The previous head was 0007. Insert a member there, then upgrade
    to 0008 and confirm the new column exists with the server_default
    applied to the existing row.

    This is the bug-regression path: an earlier draft of this migration
    used `op.batch_alter_table`, which on SQLite recreates the entire
    `members` table to add a NOT NULL column. The recreate fires
    `ON DELETE CASCADE` against `member_stats` (and every other FK
    referencing members), wiping unrelated data. The migration now
    uses native `op.add_column` to avoid the recreate.
    """
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "0007_add_rewards")
    with sqlite3.connect(db) as conn:
        _seed_member(conn, member_id=1)
        # Also insert a member_stats row so we can verify it survives.
        conn.execute(
            "INSERT INTO member_stats (member_id, points_total, "
            "points_this_week, streak, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (1, 42, 7, 3),
        )
        conn.commit()

    command.upgrade(_alembic_config(db), "head")

    with sqlite3.connect(db) as conn:
        # The new column applies the server_default to the existing row.
        row = conn.execute(
            "SELECT calendar_entity_ids FROM members WHERE id = 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "[]", (
            "existing members should pick up '[]' via server_default"
        )
        # member_stats survives the migration (regression for the
        # batch_alter_table cascade-delete bug).
        stats = conn.execute(
            "SELECT points_total FROM member_stats WHERE member_id = 1"
        ).fetchone()
        assert stats is not None
        assert stats[0] == 42, (
            "member_stats must survive the migration — the batch_alter "
            "bug used to wipe it. See migration 0008 docstring."
        )


def test_household_settings_accepts_null_household_id_pk(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        # Single-tenant addon mode — household_id is NULL. SQLite
        # allows NULL in a single-column PK (matches the convention
        # used by household_starter_suppression).
        conn.execute(
            "INSERT INTO household_settings "
            "(household_id, shared_calendar_entity_ids, created_at, updated_at) "
            "VALUES (NULL, '[\"calendar.family\"]', datetime('now'), datetime('now'))"
        )
        conn.commit()
        row = conn.execute(
            "SELECT shared_calendar_entity_ids FROM household_settings"
        ).fetchone()
        assert row[0] == '["calendar.family"]'


def test_calendar_entity_ids_accepts_json_list(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO members (id, name, slug, color, display_mode, "
            "requires_approval, calendar_entity_ids, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (
                1,
                "Bob",
                "bob",
                "#00f",
                "kid_standard",
                0,
                '["calendar.bob_school","calendar.bob_soccer"]',
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT calendar_entity_ids FROM members WHERE id = 1"
        ).fetchone()
        assert row[0] == '["calendar.bob_school","calendar.bob_soccer"]'


def test_downgrade_removes_both(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    command.downgrade(_alembic_config(db), "0007_add_rewards")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "members")
        assert "calendar_entity_ids" not in cols
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "household_settings" not in tables
        # Other tables preserved.
        assert "members" in tables
        assert "reward" in tables


def test_upgrade_downgrade_upgrade_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    command.downgrade(_alembic_config(db), "0007_add_rewards")
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "members")
        assert "calendar_entity_ids" in cols
