"""Declarative base + async engine / session factories.

The PRAGMA connect-event hook lives in `pragmas.py` so non-engine callers
(Alembic env, test fixtures) can import it independently. Datetimes are
stored as naive UTC — see `family_chores_core.time.utcnow`.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from family_chores_db.pragmas import install_sqlite_pragmas


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_async_db_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path}"


def make_sync_db_url(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def make_async_engine(db_path: Path) -> AsyncEngine:
    engine = create_async_engine(make_async_db_url(db_path), future=True)
    install_sqlite_pragmas(engine.sync_engine)
    return engine


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
