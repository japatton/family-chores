"""SQLite PRAGMA connect-event hook.

Every SQLite connection produced by an engine that was passed through
`install_sqlite_pragmas` gets `foreign_keys=ON`, `journal_mode=WAL`, and
`synchronous=NORMAL` applied. See DECISIONS §4 #24 for why this is wired
through SQLAlchemy's `connect` event rather than executed once on the
engine: pooled connections each go through `connect`, including the ones
Alembic opens — without this, a pooled connection would silently lose
the PRAGMAs.

Extracted to its own module in Phase 2 step 3 so callers that only need
the hook (e.g. Alembic's `env.py`, test fixtures) don't have to import
the engine factory from `base.py`. The leading underscore was dropped
when the helper became part of the public package surface.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.engine import Engine


def install_sqlite_pragmas(sync_engine: Engine) -> None:
    """Wire `connect`-event PRAGMAs onto the given sync SQLAlchemy engine.

    Pass an `AsyncEngine`'s `.sync_engine` for async-mode use.
    """

    @event.listens_for(sync_engine, "connect")
    def _on_connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
