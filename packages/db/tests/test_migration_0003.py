"""End-to-end test for the `0003_add_household_id` Alembic migration.

This is the **only** test in the suite that actually invokes Alembic
(everything else uses `Base.metadata.create_all` for speed). It exercises
the same code path the addon's startup uses
(`family_chores_db.recovery.default_alembic_upgrade`), so a regression
in the migration script itself surfaces here.

Verifies:
  - `upgrade head` from a clean DB applies 0001 + 0002 + 0003 cleanly.
  - Every tenant-scoped table gains a `household_id VARCHAR(36)` column
    + a `ix_<table>_household_id` index.
  - Rows that existed before 0003 keep `household_id = NULL` after.
  - `downgrade -1` removes both the column and the index from every
    table without losing any pre-existing row data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

# The 7 tenant-scoped tables; mirrors `_SCOPED_TABLES` in the migration.
_SCOPED_TABLES: tuple[str, ...] = (
    "members",
    "chores",
    "chore_assignments",
    "chore_instances",
    "member_stats",
    "activity_log",
    "app_config",
)

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


def _indexes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}


# ─── upgrade ──────────────────────────────────────────────────────────────


def test_upgrade_head_adds_household_id_column_to_every_scoped_table(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")

    with sqlite3.connect(db) as conn:
        for table in _SCOPED_TABLES:
            cols = _columns(conn, table)
            assert "household_id" in cols, (
                f"{table} is missing household_id after `alembic upgrade head`"
            )


def test_upgrade_head_creates_index_on_every_scoped_table(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")

    with sqlite3.connect(db) as conn:
        for table in _SCOPED_TABLES:
            indexes = _indexes(conn, table)
            expected = f"ix_{table}_household_id"
            assert expected in indexes, (
                f"{table} is missing index {expected!r} after `alembic upgrade head` "
                f"(have: {sorted(indexes)})"
            )


def test_existing_rows_have_null_household_id(tmp_path):
    """Insert a member at the 0002 baseline, then upgrade — its row keeps NULL."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)

    command.upgrade(cfg, "0002_member_ha_todo")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO members "
            "(name, slug, color, display_mode, requires_approval, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("Alice", "alice", "#ff00ff", "kid_standard", 0),
        )
        conn.commit()

    command.upgrade(cfg, "head")

    with sqlite3.connect(db) as conn:
        rows = list(conn.execute("SELECT name, household_id FROM members"))
    assert rows == [("Alice", None)], (
        "pre-existing rows must keep household_id = NULL after the upgrade"
    )


# ─── downgrade ────────────────────────────────────────────────────────────


def test_downgrade_removes_column_and_index_without_data_loss(tmp_path):
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)

    command.upgrade(cfg, "head")
    with sqlite3.connect(db) as conn:
        # Insert one member with a household_id (multi-tenant-style row)
        # and one without (single-tenant-style row) — both must survive
        # the downgrade with their non-tenant fields intact.
        conn.execute(
            "INSERT INTO members "
            "(name, slug, color, display_mode, requires_approval, "
            "household_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("Bob", "bob", "#00ff00", "kid_standard", 0, "household-x"),
        )
        conn.execute(
            "INSERT INTO members "
            "(name, slug, color, display_mode, requires_approval, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("Carol", "carol", "#0000ff", "kid_standard", 0),
        )
        conn.commit()

    command.downgrade(cfg, "0002_member_ha_todo")

    with sqlite3.connect(db) as conn:
        for table in _SCOPED_TABLES:
            cols = _columns(conn, table)
            assert "household_id" not in cols, (
                f"{table} still has household_id column after downgrade"
            )
            indexes = _indexes(conn, table)
            assert f"ix_{table}_household_id" not in indexes, (
                f"{table} still has the household_id index after downgrade"
            )

        # Both rows survived; non-tenant fields intact.
        rows = sorted(conn.execute("SELECT name, slug FROM members"))
    assert rows == [("Bob", "bob"), ("Carol", "carol")]


# ─── round-trip ───────────────────────────────────────────────────────────


def test_upgrade_then_downgrade_then_upgrade_is_idempotent(tmp_path):
    """Catches migrations that work once but break on re-application."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0002_member_ha_todo")
    command.upgrade(cfg, "head")

    with sqlite3.connect(db) as conn:
        for table in _SCOPED_TABLES:
            assert "household_id" in _columns(conn, table)


# ─── parametrized smoke per table ─────────────────────────────────────────


@pytest.mark.parametrize("table", _SCOPED_TABLES)
def test_household_id_is_varchar_36_nullable(tmp_path, table):
    """Per-table type + nullability check — easy to spot which table broke."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")

    with sqlite3.connect(db) as conn:
        info = list(conn.execute(f"PRAGMA table_info({table})"))
    by_name = {row[1]: row for row in info}
    col = by_name["household_id"]
    # PRAGMA table_info row: (cid, name, type, notnull, dflt_value, pk)
    assert col[2].upper().startswith("VARCHAR"), (
        f"{table}.household_id type is {col[2]!r}, expected VARCHAR(36)"
    )
    assert col[3] == 0, f"{table}.household_id is NOT NULL — should be nullable"
    assert col[5] == 0, f"{table}.household_id is part of the PK — it shouldn't be"
