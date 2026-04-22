"""Declarative base + async engine factory.

Every SQLite connection gets `PRAGMA foreign_keys=ON`, `journal_mode=WAL`, and
`synchronous=NORMAL` applied via the `connect` event. Datetimes are stored as
naive UTC — see `family_chores.core.time.utcnow`.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_async_db_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def make_sync_db_url(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def _install_sqlite_pragmas(sync_engine: Engine) -> None:
    @event.listens_for(sync_engine, "connect")
    def _on_connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()


def make_async_engine(db_path: Path) -> AsyncEngine:
    engine = create_async_engine(make_async_db_url(db_path), future=True)
    _install_sqlite_pragmas(engine.sync_engine)
    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
