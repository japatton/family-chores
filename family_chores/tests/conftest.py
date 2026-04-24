"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Ensure the package under `src/` is importable without installing it.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from family_chores_addon.app import create_app  # noqa: E402
from family_chores_addon.config import Options  # noqa: E402
from family_chores_db.base import Base  # noqa: E402
from family_chores_db.pragmas import install_sqlite_pragmas  # noqa: E402


@pytest.fixture
async def async_engine(tmp_path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'async.db'}", future=True)
    install_sqlite_pragmas(engine.sync_engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def async_session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


@pytest.fixture
async def async_session(
    async_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


# ─── API fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def api_options(tmp_path) -> Options:
    return Options(
        log_level="debug",
        week_starts_on="monday",
        sound_default=False,
        timezone_override="UTC",
        data_dir=tmp_path,
    )


@pytest.fixture
def client(api_options, monkeypatch) -> Iterator[TestClient]:
    """A TestClient with the full lifespan run — DB bootstrapped, WSManager
    up, JWT secret ensured, catch-up rollover executed. Scheduler is
    skipped so pytest's loop doesn't inherit background threads."""
    monkeypatch.setenv("FAMILY_CHORES_SKIP_SCHEDULER", "1")
    app = create_app(options=api_options)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def parent_headers(client) -> dict[str, str]:
    """Returns Authorization header with a valid parent JWT, after setting
    the parent PIN to '1234'."""
    r = client.post("/api/auth/pin/set", json={"pin": "1234"})
    assert r.status_code == 200, r.text
    r = client.post("/api/auth/pin/verify", json={"pin": "1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
