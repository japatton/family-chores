"""End-to-end tests for the `0009_activity_log_index` Alembic migration.

D-6 from the v0.5.0 ultra-review: adds composite
`ix_activity_log_household_ts` so the canonical paginated query in
`routers/admin.py:list_activity` doesn't sort. Pure additive index;
covered by upgrade, downgrade, and round-trip tests.
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


def _indexes_on(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND tbl_name=?",
            (table,),
        )
    }


def test_upgrade_head_creates_composite_index(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        assert "ix_activity_log_household_ts" in _indexes_on(conn, "activity_log")


def test_existing_per_column_indexes_remain(tmp_path):
    """The composite is purely additive — the existing `ts` and
    `action` single-column indexes (created in earlier migrations)
    must still be present after 0009 lands."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        indexes = _indexes_on(conn, "activity_log")
        assert "ix_activity_log_household_ts" in indexes
        # The single-column indexes are SQLAlchemy-generated; their
        # auto-names are `ix_activity_log_<column>`. Verify both are
        # present so we didn't accidentally drop them.
        assert "ix_activity_log_ts" in indexes
        assert "ix_activity_log_action" in indexes


def test_downgrade_removes_only_the_composite(tmp_path):
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0008_add_calendar")
    with sqlite3.connect(db) as conn:
        indexes = _indexes_on(conn, "activity_log")
        assert "ix_activity_log_household_ts" not in indexes
        # Other indexes survive.
        assert "ix_activity_log_ts" in indexes
        assert "ix_activity_log_action" in indexes


def test_round_trip_is_idempotent(tmp_path):
    """upgrade → downgrade → upgrade leaves the schema identical."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "head")
    indexes_after_first = _indexes_on(sqlite3.connect(db), "activity_log")
    command.downgrade(cfg, "0008_add_calendar")
    command.upgrade(cfg, "head")
    indexes_after_round = _indexes_on(sqlite3.connect(db), "activity_log")
    assert indexes_after_first == indexes_after_round


def test_seeded_rows_survive_upgrade(tmp_path):
    """Migration is additive — inserting rows before the upgrade must
    leave the rows untouched."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)
    command.upgrade(cfg, "0008_add_calendar")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO activity_log (ts, actor, action, payload, household_id) "
            "VALUES (datetime('now'), ?, ?, '{}', NULL)",
            ("seed", "test"),
        )
        conn.commit()
    command.upgrade(cfg, "head")
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT actor, action FROM activity_log"
        ).fetchone()
        assert row == ("seed", "test")
