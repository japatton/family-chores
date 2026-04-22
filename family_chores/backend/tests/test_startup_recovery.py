"""Startup-time DB integrity / recovery tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine

from family_chores.db.base import Base
from family_chores.db.startup import bootstrap_db


def _fake_migrations(db_path: Path) -> None:
    """Stand-in for `alembic upgrade head` — creates all tables synchronously."""
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()


def _write_good_db(path: Path) -> None:
    _fake_migrations(path)
    # Insert a sentinel row so we can assert restore-vs-fresh.
    with sqlite3.connect(path) as conn:
        conn.execute(
            "INSERT INTO members (name, slug, color, display_mode, requires_approval, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            ("Sentinel", "sentinel", "#000000", "kid_standard", 0),
        )


def _corrupt(path: Path) -> None:
    """Simulate full DB corruption.

    Just overwriting the main file is not enough — in WAL mode SQLite can
    still recover using the WAL sidecar, so we delete those too.
    """
    path.write_bytes(b"this is not a sqlite database")
    for sfx in ("-wal", "-shm", "-journal"):
        side = path.with_name(path.name + sfx)
        if side.exists():
            side.unlink()


def _members(path: Path) -> list[str]:
    with sqlite3.connect(path) as conn:
        cur = conn.execute("SELECT slug FROM members ORDER BY slug")
        return [row[0] for row in cur.fetchall()]


def test_fresh_install_initialized(tmp_path):
    result = bootstrap_db(tmp_path / "chores.db", run_migrations=_fake_migrations)
    assert result.action == "initialized"
    assert result.banner is None
    assert result.db_path.exists()
    # .bak is only written on a subsequent boot when the DB is healthy.
    assert not result.bak_path.exists()
    assert _members(result.db_path) == []


def test_second_boot_writes_backup(tmp_path):
    db = tmp_path / "chores.db"
    bootstrap_db(db, run_migrations=_fake_migrations)  # first boot
    _write_good_db(db)  # pretend app inserted data

    result = bootstrap_db(db, run_migrations=_fake_migrations)  # second boot

    assert result.action == "migrated"
    assert result.banner is None
    assert result.bak_path.exists()
    assert _members(result.bak_path) == ["sentinel"]


def test_corrupt_db_restored_from_backup(tmp_path):
    db = tmp_path / "chores.db"
    bak = db.with_name(db.name + ".bak")

    _write_good_db(bak)
    _corrupt(db)

    result = bootstrap_db(db, run_migrations=_fake_migrations)

    assert result.action == "restored_backup"
    assert result.banner is not None
    assert "restored from backup" in result.banner.lower()
    assert _members(db) == ["sentinel"]
    # The corrupt original should be retained for debugging.
    assert any(p.name.startswith("chores.db.corrupt-") for p in tmp_path.iterdir())


def test_corrupt_db_no_backup_starts_fresh(tmp_path):
    db = tmp_path / "chores.db"
    _corrupt(db)

    result = bootstrap_db(db, run_migrations=_fake_migrations)

    assert result.action == "reset_corrupt"
    assert result.banner is not None
    assert "no usable backup" in result.banner.lower()
    assert _members(db) == []
    assert any(p.name.startswith("chores.db.corrupt-") for p in tmp_path.iterdir())


def test_corrupt_db_corrupt_backup_starts_fresh(tmp_path):
    db = tmp_path / "chores.db"
    bak = db.with_name(db.name + ".bak")
    _corrupt(db)
    _corrupt(bak)

    result = bootstrap_db(db, run_migrations=_fake_migrations)

    assert result.action == "reset_corrupt"
    assert result.banner is not None
    assert _members(db) == []


def test_empty_zero_byte_db_treated_as_corrupt(tmp_path):
    db = tmp_path / "chores.db"
    db.touch()  # zero-byte file, not a valid SQLite DB
    bak = db.with_name(db.name + ".bak")
    _write_good_db(bak)

    result = bootstrap_db(db, run_migrations=_fake_migrations)

    assert result.action == "restored_backup"
    assert _members(db) == ["sentinel"]


def test_run_migrations_called_on_every_path(tmp_path):
    calls: list[Path] = []

    def spy(db_path: Path) -> None:
        calls.append(db_path)
        _fake_migrations(db_path)

    db = tmp_path / "chores.db"
    bootstrap_db(db, run_migrations=spy)
    assert calls == [db]

    bootstrap_db(db, run_migrations=spy)
    assert calls == [db, db]

    _corrupt(db)
    bootstrap_db(db, run_migrations=spy)
    assert calls == [db, db, db]
