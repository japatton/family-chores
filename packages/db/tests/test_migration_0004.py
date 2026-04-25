"""End-to-end tests for the `0004_add_chore_templates` Alembic migration.

Same shape as `test_migration_0003.py` — invokes Alembic against a real
SQLite file so a regression in the migration script (or its interaction
with the existing table set) surfaces here.

Verifies:

  - `upgrade head` from a clean DB applies 0001..0004 and creates both
    new tables (`chore_template`, `household_starter_suppression`) plus
    the two new columns on `chores` (`template_id`, `ephemeral`).
  - Existing `chores` rows get `template_id=NULL`, `ephemeral=0` (the
    server_default) after the upgrade.
  - The (household_id, name_normalized) and (household_id, starter_key)
    unique constraints are enforced.
  - The composite PK on `household_starter_suppression` is enforced.
  - The CHECK constraint on `source` is enforced.
  - `downgrade -1` removes everything cleanly without losing chore data.
  - upgrade → downgrade → upgrade is idempotent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
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


def _indexes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA index_list({table})")}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchall()
    return bool(rows)


def _insert_chore_at_baseline(conn: sqlite3.Connection, name: str) -> None:
    """Insert a chore using only columns that exist before 0004."""
    conn.execute(
        "INSERT INTO chores "
        "(name, points, active, recurrence_type, recurrence_config, "
        " created_at, updated_at) "
        "VALUES (?, 1, 1, 'daily', '{}', "
        "        datetime('now'), datetime('now'))",
        (name,),
    )
    conn.commit()


# ─── upgrade ──────────────────────────────────────────────────────────────


def test_upgrade_head_creates_chore_template_table(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        assert _table_exists(conn, "chore_template")
        cols = _columns(conn, "chore_template")
        for c in (
            "id",
            "household_id",
            "name",
            "name_normalized",
            "icon",
            "category",
            "age_min",
            "age_max",
            "points_suggested",
            "default_recurrence_type",
            "default_recurrence_config",
            "description",
            "source",
            "starter_key",
            "created_at",
            "updated_at",
        ):
            assert c in cols, f"chore_template missing column {c!r}"


def test_upgrade_head_creates_suppression_table(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        assert _table_exists(conn, "household_starter_suppression")
        cols = _columns(conn, "household_starter_suppression")
        assert {"household_id", "starter_key", "suppressed_at"} <= cols


def test_upgrade_adds_template_id_and_ephemeral_to_chores(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        cols = _columns(conn, "chores")
        assert "template_id" in cols
        assert "ephemeral" in cols


def test_existing_chore_rows_get_default_template_fields(tmp_path):
    """A chore inserted at the 0003 baseline should keep its data and
    pick up template_id=NULL, ephemeral=0 after upgrade."""
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)

    command.upgrade(cfg, "0003_add_household_id")
    with sqlite3.connect(db) as conn:
        _insert_chore_at_baseline(conn, "Pre-existing chore")

    command.upgrade(cfg, "head")

    with sqlite3.connect(db) as conn:
        rows = list(
            conn.execute("SELECT name, template_id, ephemeral FROM chores")
        )
    assert rows == [("Pre-existing chore", None, 0)], (
        "pre-existing chore should keep its name + get NULL template_id + ephemeral=0"
    )


def test_chore_template_indexes_present(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        indexes = _indexes(conn, "chore_template")
        for ix in (
            "ix_chore_template_household_id",
            "ix_chore_template_name_normalized",
            "ix_chore_template_category",
            "ix_template_household_category",
        ):
            assert ix in indexes, f"chore_template missing index {ix!r}"


def test_chores_template_id_index_present(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        assert "ix_chores_template_id" in _indexes(conn, "chores")


# ─── constraints ──────────────────────────────────────────────────────────


def _insert_template(
    conn: sqlite3.Connection,
    *,
    id: str,
    name: str,
    name_normalized: str,
    household_id: str | None = None,
    source: str = "custom",
    starter_key: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO chore_template "
        "(id, household_id, name, name_normalized, "
        " default_recurrence_type, default_recurrence_config, "
        " source, starter_key, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'daily', '{}', ?, ?, "
        "        datetime('now'), datetime('now'))",
        (id, household_id, name, name_normalized, source, starter_key),
    )


def test_unique_household_name_normalized(tmp_path):
    """The (household_id, name_normalized) UQ fires when household_id is
    set. See `test_null_household_does_not_dedup_*` below for the SQLite
    NULL-distinct gotcha."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        _insert_template(
            conn,
            id="t1",
            household_id="household-x",
            name="Make Bed",
            name_normalized="make bed",
        )
        # SQLite's IntegrityError text is "UNIQUE constraint failed:
        # chore_template.household_id, chore_template.name_normalized" —
        # it lists the columns rather than the constraint name. Match
        # the columns to be SQLite-portable.
        with pytest.raises(
            sqlite3.IntegrityError,
            match=r"UNIQUE constraint failed.*household_id.*name_normalized",
        ):
            _insert_template(
                conn,
                id="t2",
                household_id="household-x",
                name="Make bed",
                name_normalized="make bed",
            )


def test_unique_household_starter_key(tmp_path):
    """Same constraint, different column pair — exercised against a real
    household_id so the UQ actually fires."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        _insert_template(
            conn,
            id="t1",
            household_id="household-x",
            name="A",
            name_normalized="a",
            source="starter",
            starter_key="make_bed",
        )
        with pytest.raises(
            sqlite3.IntegrityError,
            match=r"UNIQUE constraint failed.*household_id.*starter_key",
        ):
            _insert_template(
                conn,
                id="t2",
                household_id="household-x",
                name="B",
                name_normalized="b",
                source="starter",
                starter_key="make_bed",
            )


def test_null_household_does_not_dedup_via_constraint(tmp_path):
    """Documents the SQLite NULL-distinct behavior on UQ constraints.

    Two rows with (NULL household_id, same name_normalized) coexist
    because SQLite treats NULL as distinct in UNIQUE per the SQL
    standard. In single-tenant addon mode (where every row has
    household_id=NULL), dedup is enforced at the application layer
    instead — the seeder does a SELECT first and the API returns 409
    on conflict. The constraint becomes load-bearing in multi-tenant
    SaaS where household_id is non-null.

    Pinned as a regression test so a future schema change that tries
    to "fix" this would have to touch this test and force a discussion.
    """
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        _insert_template(conn, id="t1", name="Make Bed", name_normalized="make bed")
        # Should NOT raise — this is the documented SQLite behavior.
        _insert_template(conn, id="t2", name="Make bed", name_normalized="make bed")
        rows = list(
            conn.execute(
                "SELECT COUNT(*) FROM chore_template WHERE name_normalized=?",
                ("make bed",),
            )
        )
        assert rows[0][0] == 2, "two NULL-household rows should coexist in SQLite"


def test_source_check_constraint_rejects_other_values(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="ck_template_source_enum"):
            _insert_template(
                conn, id="t1", name="X", name_normalized="x", source="invalid"
            )


def test_points_check_constraint_rejects_negative(tmp_path):
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        with pytest.raises(
            sqlite3.IntegrityError, match="ck_template_points_nonneg"
        ):
            conn.execute(
                "INSERT INTO chore_template "
                "(id, name, name_normalized, points_suggested, "
                " default_recurrence_type, default_recurrence_config, "
                " source, created_at, updated_at) "
                "VALUES ('t1', 'X', 'x', -5, 'daily', '{}', 'custom', "
                "        datetime('now'), datetime('now'))"
            )


def test_suppression_composite_pk_enforced(tmp_path):
    """Composite PK fires when household_id is set. The NULL case is the
    same SQLite-NULL-in-PK gotcha documented for the UQ constraints
    above — exercised in `test_null_household_suppression_does_not_dedup`."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO household_starter_suppression "
            "(household_id, starter_key, suppressed_at) "
            "VALUES ('household-x', 'make_bed', datetime('now'))"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO household_starter_suppression "
                "(household_id, starter_key, suppressed_at) "
                "VALUES ('household-x', 'make_bed', datetime('now'))"
            )


def test_null_household_suppression_does_not_dedup_via_pk(tmp_path):
    """SQLite allows NULL in composite PK columns and treats NULLs as
    distinct — same gotcha as the UQ constraints. Single-tenant addon
    mode relies on the application layer to prevent double-suppression."""
    db = tmp_path / "test.db"
    command.upgrade(_alembic_config(db), "head")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO household_starter_suppression "
            "(household_id, starter_key, suppressed_at) "
            "VALUES (NULL, 'make_bed', datetime('now'))"
        )
        # Should NOT raise.
        conn.execute(
            "INSERT INTO household_starter_suppression "
            "(household_id, starter_key, suppressed_at) "
            "VALUES (NULL, 'make_bed', datetime('now'))"
        )
        rows = list(
            conn.execute(
                "SELECT COUNT(*) FROM household_starter_suppression "
                "WHERE starter_key=?",
                ("make_bed",),
            )
        )
        assert rows[0][0] == 2, "two NULL-household rows should coexist in SQLite"


# ─── downgrade ────────────────────────────────────────────────────────────


def test_downgrade_removes_new_tables_and_columns(tmp_path):
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)

    command.upgrade(cfg, "head")
    with sqlite3.connect(db) as conn:
        _insert_chore_at_baseline(conn, "survives downgrade")

    command.downgrade(cfg, "0003_add_household_id")

    with sqlite3.connect(db) as conn:
        assert not _table_exists(conn, "chore_template")
        assert not _table_exists(conn, "household_starter_suppression")
        cols = _columns(conn, "chores")
        assert "template_id" not in cols
        assert "ephemeral" not in cols
        # Chore data survived the downgrade.
        rows = list(conn.execute("SELECT name FROM chores"))
        assert rows == [("survives downgrade",)]


# ─── round-trip ───────────────────────────────────────────────────────────


def test_upgrade_then_downgrade_then_upgrade_is_idempotent(tmp_path):
    db = tmp_path / "test.db"
    cfg = _alembic_config(db)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0003_add_household_id")
    command.upgrade(cfg, "head")

    with sqlite3.connect(db) as conn:
        assert _table_exists(conn, "chore_template")
        assert _table_exists(conn, "household_starter_suppression")
        cols = _columns(conn, "chores")
        assert "template_id" in cols
        assert "ephemeral" in cols
