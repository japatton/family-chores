"""FastAPI application factory.

The `lifespan` context handles:
  1. DB bootstrap (integrity check → WAL-aware backup → alembic → recovery).
  2. Async engine + session factory creation.
  3. **Startup catch-up rollover** — if the app was down when midnight fired,
     this runs the same rollover pipeline as the scheduled job so the DB is
     consistent from the very first request.
  4. APScheduler startup (midnight cron + 15-min HA-reconcile stub).
  5. Graceful shutdown of scheduler + engine.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from family_chores import __version__
from family_chores.config import Options, load_options
from family_chores.core.time import local_today
from family_chores.db.base import make_async_engine, make_session_factory
from family_chores.db.startup import BootstrapResult, bootstrap_db
from family_chores.scheduler import make_scheduler
from family_chores.services.rollover_service import run_rollover

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Tests (and anything using `with TestClient(app)`) can set this to "1" to
# skip APScheduler startup — otherwise the event loop ends up with two
# scheduler threads per TestClient and teardown becomes noisy.
_SKIP_SCHEDULER_ENV = "FAMILY_CHORES_SKIP_SCHEDULER"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    opts = cast(Options, app.state.options)

    app.state.bootstrap = bootstrap_db(opts.db_path, opts.db_backup_path)
    app.state.engine = make_async_engine(opts.db_path)
    app.state.session_factory = make_session_factory(app.state.engine)

    tz = opts.effective_timezone

    try:
        async with app.state.session_factory() as session:
            summary = await run_rollover(
                session, today=local_today(tz), week_starts_on=opts.week_starts_on
            )
            await session.commit()
            log.info(
                "startup catch-up rollover: date=%s missed=%d generated=%d members=%d",
                summary.date,
                summary.instances_missed,
                summary.instances_generated,
                summary.members_updated,
            )
    except Exception:
        log.exception("startup catch-up rollover failed; continuing")

    app.state.scheduler = None
    if os.environ.get(_SKIP_SCHEDULER_ENV) != "1":
        scheduler = make_scheduler(
            app.state.session_factory, tz=tz, week_starts_on=opts.week_starts_on
        )
        scheduler.start()
        app.state.scheduler = scheduler

    try:
        yield
    finally:
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown(wait=False)
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
            "timezone": opts.effective_timezone,
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
