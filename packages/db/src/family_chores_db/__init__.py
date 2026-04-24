"""Database layer for Family Chores.

Owns SQLAlchemy models, Alembic migrations, the engine/session factory, the
SQLite PRAGMA connect hooks, and the WAL-aware recovery/backup utilities.

Apps construct engines via `make_async_engine(db_path)` and call
`recovery.bootstrap_db(...)` from their own lifespan. This package MUST
stay free of HA-specific dependencies.

The `models` submodule is re-exported eagerly so importing
`family_chores_db` registers every ORM table on `Base.metadata` — required
for `Base.metadata.create_all` and Alembic autogenerate to see all tables.
"""

from family_chores_db import models  # noqa: F401 — registers tables on Base.metadata
from family_chores_db.base import (
    Base,
    make_async_db_url,
    make_async_engine,
    make_session_factory,
    make_sync_db_url,
)
from family_chores_db.scoped import scoped

__all__ = [
    "Base",
    "make_async_db_url",
    "make_async_engine",
    "make_session_factory",
    "make_sync_db_url",
    "models",
    "scoped",
]
