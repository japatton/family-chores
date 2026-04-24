"""Startup bootstrap: integrity check → backup → migrate → recover.

Flow per `bootstrap_db`:

1. Ensure `data_dir` exists.
2. If the DB file exists and passes integrity:
   - Checkpoint WAL into the main DB file, then copy to `.bak`. This gives
     us a single-file, self-contained backup — simply copying the main DB
     when WAL mode is active would produce a torn snapshot that's missing
     anything the app wrote since the last checkpoint.
3. If integrity fails:
   - If `.bak` exists and passes integrity, move the corrupt file (and any
     -wal/-shm sidecars) aside and restore from the backup. Return a banner.
   - Else move the corrupt files aside and start fresh. Return a banner.
4. Run `alembic upgrade head` via the injected `run_migrations`.

The alembic invocation is injected so tests can swap in a fast
`Base.metadata.create_all` without spinning up Alembic.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from family_chores_core.time import utcnow

log = logging.getLogger(__name__)

BootstrapAction = Literal["initialized", "migrated", "restored_backup", "reset_corrupt"]

_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    action: BootstrapAction
    banner: str | None
    db_path: Path
    bak_path: Path


def _sidecars(path: Path) -> list[Path]:
    return [path.with_name(path.name + sfx) for sfx in _SIDECAR_SUFFIXES]


def _integrity_ok(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            cursor = conn.execute("PRAGMA integrity_check")
            row = cursor.fetchone()
            return bool(row and row[0] == "ok")
    except sqlite3.DatabaseError:
        return False


def _move_aside(path: Path) -> Path:
    """Move `path` and its WAL/SHM sidecars to a timestamped `.corrupt-…` name.

    Sidecars go along so the next process can't accidentally resurrect a
    WAL overlay on top of a restored or freshly-initialised main file.
    """
    ts = utcnow().strftime("%Y%m%dT%H%M%S")
    target = path.with_name(f"{path.name}.corrupt-{ts}")
    shutil.move(str(path), str(target))
    for sidecar in _sidecars(path):
        if sidecar.exists():
            sidecar_target = sidecar.with_name(f"{path.name}.corrupt-{ts}{sidecar.suffix}")
            shutil.move(str(sidecar), str(sidecar_target))
    return target


def _snapshot_to(src: Path, dest: Path) -> None:
    """Produce a WAL-aware single-file snapshot of `src` at `dest`.

    Forces a TRUNCATE checkpoint so the main DB file contains the full
    committed state, then byte-copies. Cheaper than `sqlite3.Connection.backup`
    for our size and simpler to reason about.
    """
    with sqlite3.connect(str(src)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy2(src, dest)


def _restore_from(src: Path, dest: Path) -> None:
    """Restore `src` onto `dest`, clearing any lingering sidecars first."""
    for sidecar in _sidecars(dest):
        if sidecar.exists():
            sidecar.unlink()
    shutil.copy2(src, dest)


def default_alembic_upgrade(db_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    migrations_dir = Path(__file__).resolve().parent / "migrations"
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def bootstrap_db(
    db_path: Path,
    bak_path: Path | None = None,
    run_migrations: Callable[[Path], None] | None = None,
) -> BootstrapResult:
    bak_path = bak_path if bak_path is not None else db_path.with_name(db_path.name + ".bak")
    run_migrations = run_migrations if run_migrations is not None else default_alembic_upgrade

    db_path.parent.mkdir(parents=True, exist_ok=True)

    banner: str | None = None
    action: BootstrapAction = "initialized"

    if db_path.exists():
        if _integrity_ok(db_path):
            _snapshot_to(db_path, bak_path)
            action = "migrated"
        else:
            aside = _move_aside(db_path)
            log.error("database integrity check failed; moved %s -> %s", db_path, aside)
            if _integrity_ok(bak_path):
                _restore_from(bak_path, db_path)
                action = "restored_backup"
                banner = (
                    f"Database was restored from backup after corruption "
                    f"(corrupt copy retained at {aside.name})."
                )
                log.warning("restored DB from backup %s", bak_path)
            else:
                action = "reset_corrupt"
                banner = (
                    f"Database was corrupt and no usable backup existed; started fresh "
                    f"(corrupt copy retained at {aside.name})."
                )
                log.error("no usable backup; starting with a fresh DB")

    run_migrations(db_path)

    return BootstrapResult(action=action, banner=banner, db_path=db_path, bak_path=bak_path)
