"""Add-on FastAPI app factory — wraps `family_chores_api.create_app`.

Owns the addon-specific concerns that the shared factory deliberately
doesn't know about:

  - Lifespan sequence (DB bootstrap → engine + session factory → JWT
    secret → WSManager → effective timezone → HA bridge → catch-up
    rollover + reconcile → APScheduler).
  - `/api/info` endpoint (exposes addon options + ha_connected + bootstrap
    banner — none of these apply to the future SaaS deployment).
  - SPA static-file mount at `/`.

The shared factory in `packages/api` provides the routers, error handlers,
request-ID middleware, and `/api/health`. See DECISIONS §11 step 4.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from family_chores_api import WSManager
from family_chores_api import create_app as create_api_app
from family_chores_api.security import ensure_jwt_secret
from family_chores_api.services.rollover_service import run_rollover
from family_chores_api.services.starter_seeding import seed_starter_library
from family_chores_core.time import local_today
from family_chores_db.base import make_async_engine, make_session_factory
from family_chores_db.recovery import BootstrapResult, bootstrap_db
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from family_chores_addon import __version__
from family_chores_addon.auth import IngressAuthStrategy
from family_chores_addon.config import Options, load_options
from family_chores_addon.ha import HABridge, NoOpBridge, make_client_from_env
from family_chores_addon.ha.client import HAClient, HAClientError
from family_chores_addon.ha.reconcile import reconcile_once
from family_chores_addon.scheduler import make_scheduler

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
_SKIP_SCHEDULER_ENV = "FAMILY_CHORES_SKIP_SCHEDULER"


async def _resolve_effective_timezone(opts: Options, client: HAClient | None) -> str:
    """Prefer explicit override; else try HA's `/api/config → time_zone`; else UTC."""
    if opts.timezone_override:
        return opts.timezone_override
    if client is not None:
        try:
            cfg = await client.get_config()
            tz = cfg.get("time_zone")
            if isinstance(tz, str) and tz:
                return tz
        except HAClientError as exc:
            log.info("HA /config fetch failed (%s); defaulting to UTC", exc)
        except Exception:
            log.exception("unexpected error fetching HA /config; defaulting to UTC")
    return "UTC"


def _bootstrap_payload(app: FastAPI) -> dict[str, str | None] | None:
    result: BootstrapResult | None = getattr(app.state, "bootstrap", None)
    if result is None:
        return None
    return {"action": result.action, "banner": result.banner}


def _build_lifespan(opts: Options):  # type: ignore[no-untyped-def]
    """Construct the addon lifespan, capturing `opts` in the closure.

    The lifespan owns every collaborator that `family_chores_api.deps`
    reads off `app.state` (session_factory, bridge, ws_manager, jwt_secret,
    effective_timezone, week_starts_on). Without these slots populated,
    every router would 500.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.options = opts
        app.state.week_starts_on = opts.week_starts_on

        app.state.bootstrap = bootstrap_db(opts.db_path, opts.db_backup_path)
        app.state.engine = make_async_engine(opts.db_path)
        app.state.session_factory = make_session_factory(app.state.engine)
        app.state.ws_manager = WSManager()

        async with app.state.session_factory() as session:
            app.state.jwt_secret = await ensure_jwt_secret(session)

        # Starter library seeding — idempotent. Runs every startup; only
        # inserts entries that aren't already present and aren't in the
        # household's suppression list. New library versions add their
        # new entries to existing households here. See DECISIONS §13 §4.
        # Single-tenant addon mode = household_id None.
        try:
            async with app.state.session_factory() as session:
                await seed_starter_library(session, household_id=None)
                await session.commit()
        except Exception:
            log.exception("starter library seed failed; continuing")

        # Auth strategy installs after the JWT secret is on app.state — the
        # strategy reads it lazily via this closure rather than capturing
        # a stale value, so a future secret-rotation endpoint can flip it
        # in-place without re-constructing the strategy.
        app.state.auth_strategy = IngressAuthStrategy(
            secret_provider=lambda: cast(str, app.state.jwt_secret)
        )

        ha_client = make_client_from_env()
        app.state.ha_client = ha_client
        tz = await _resolve_effective_timezone(opts, ha_client)
        app.state.effective_timezone = tz

        if ha_client is None:
            app.state.bridge = NoOpBridge()
        else:
            app.state.bridge = HABridge(
                ha_client,
                app.state.session_factory,
                # F-S002 fix: read the effective tz lazily off app.state
                # so the bridge's `_today_progress_pct` uses the user-
                # local date rather than UTC. Same callable shape as the
                # auth strategy's secret_provider.
                timezone_provider=lambda: cast(str, app.state.effective_timezone),
            )
        await app.state.bridge.start()

        # F-S004 fix: surface a rollover failure into /api/info so the SPA
        # can render a banner. Don't fail-fast — the addon serves degraded-
        # but-running better than crash-looping on a transient error.
        app.state.rollover_warning = None
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
        except Exception as exc:
            log.exception("startup catch-up rollover failed; continuing")
            # Truncate so a giant traceback's first-line representation
            # doesn't blow up /api/info responses. The full traceback is
            # in the addon log via log.exception above.
            summary = f"{type(exc).__name__}: {exc}"
            app.state.rollover_warning = summary[:500]

        # Startup reconcile — converges HA todo state with SQLite after any
        # downtime. Best-effort: a network blip doesn't block the app from
        # coming up; the 15-min periodic reconciler will retry.
        if ha_client is not None:
            try:
                rec = await reconcile_once(
                    ha_client, app.state.session_factory, today=local_today(tz)
                )
                log.info(
                    "startup reconcile: members=%d created=%d updated=%d deleted=%d errors=%d",
                    rec.members_processed,
                    rec.items_created,
                    rec.items_updated,
                    rec.items_deleted,
                    len(rec.errors),
                )
            except Exception:
                log.exception("startup reconcile failed; continuing")

        app.state.scheduler = None
        if os.environ.get(_SKIP_SCHEDULER_ENV) != "1":
            scheduler = make_scheduler(
                app.state.session_factory,
                tz=tz,
                week_starts_on=opts.week_starts_on,
                bridge=app.state.bridge,
                ha_client=ha_client,
            )
            scheduler.start()
            app.state.scheduler = scheduler

        try:
            yield
        finally:
            if app.state.scheduler is not None:
                app.state.scheduler.shutdown(wait=False)
            await app.state.bridge.stop()
            await app.state.engine.dispose()

    return _lifespan


def create_app(options: Options | None = None) -> FastAPI:
    opts = options if options is not None else load_options()

    app = create_api_app(
        title="Family Chores",
        version=__version__,
        lifespan=_build_lifespan(opts),
    )

    @app.get("/api/info")
    async def info() -> dict[str, object]:
        return {
            "version": __version__,
            "log_level": opts.log_level,
            "week_starts_on": opts.week_starts_on,
            "sound_default": opts.sound_default,
            "timezone": getattr(app.state, "effective_timezone", opts.effective_timezone),
            "ha_connected": getattr(app.state, "ha_client", None) is not None,
            "bootstrap": _bootstrap_payload(app),
            # F-S004: present only when startup catch-up rollover failed.
            # SPA renders a banner; the maintainer's log has the full trace.
            "rollover_warning": getattr(app.state, "rollover_warning", None),
        }

    # Static mount LAST — it catches `/` and would shadow any later routes.
    if (STATIC_DIR / "index.html").exists():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def fallback() -> str:
            return (
                "<!DOCTYPE html><html><body style='font-family:system-ui;padding:2rem'>"
                "<h1>Family Chores</h1>"
                "<p>Backend is running. SPA not built — run "
                "<code>cd frontend &amp;&amp; npm run build</code> (or let the "
                "Docker build do it for you).</p>"
                "<p>Try <code>GET /api/health</code>.</p>"
                "</body></html>"
            )

    return app
