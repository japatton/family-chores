"""FastAPI application factory.

The `lifespan` context handles DB bootstrap (integrity check → backup →
`alembic upgrade head` → recovery-from-backup if needed), then creates the
async engine + session factory and stashes them on `app.state`. Shutdown
disposes the engine.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from family_chores import __version__
from family_chores.config import Options, load_options
from family_chores.db.base import make_async_engine, make_session_factory
from family_chores.db.startup import BootstrapResult, bootstrap_db

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    opts = cast(Options, app.state.options)
    result = bootstrap_db(opts.db_path, opts.db_backup_path)
    app.state.bootstrap = result
    app.state.engine = make_async_engine(opts.db_path)
    app.state.session_factory = make_session_factory(app.state.engine)
    try:
        yield
    finally:
        await app.state.engine.dispose()


def _bootstrap_payload(app: FastAPI) -> dict[str, str | None] | None:
    result: BootstrapResult | None = getattr(app.state, "bootstrap", None)
    if result is None:
        return None
    return {"action": result.action, "banner": result.banner}


def create_app(options: Options | None = None) -> FastAPI:
    opts = options if options is not None else load_options()
    app = FastAPI(
        title="Family Chores",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    app.state.options = opts

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/info")
    async def info() -> dict[str, object]:
        return {
            "version": __version__,
            "log_level": opts.log_level,
            "week_starts_on": opts.week_starts_on,
            "sound_default": opts.sound_default,
            "bootstrap": _bootstrap_payload(app),
        }

    if STATIC_DIR.is_dir() and any(STATIC_DIR.iterdir()):
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    else:
        @app.get("/", response_class=HTMLResponse)
        async def fallback() -> str:
            return (
                "<!DOCTYPE html><html><body style='font-family:system-ui;padding:2rem'>"
                "<h1>Family Chores</h1>"
                "<p>Backend is running. Static assets not yet built — see milestone 6.</p>"
                "<p>Try <code>GET /api/health</code>.</p>"
                "</body></html>"
            )

    return app
