"""FastAPI application factory.

Lifespan sequence:
  1. Bootstrap the DB (integrity → WAL-aware backup → alembic → recovery).
  2. Create engine + session factory.
  3. Ensure the JWT secret exists in `app_config`; cache it on `app.state`.
  4. Create the WS broadcast manager.
  5. Run a catch-up rollover.
  6. Start APScheduler (unless `FAMILY_CHORES_SKIP_SCHEDULER=1`).

All routers are registered below. Errors are funnelled through a single
handler that emits `{error, detail, request_id}` and attaches an
`X-Request-ID` header so a user can correlate UI errors with backend logs.
"""

from __future__ import annotations

import logging
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from family_chores import __version__
from family_chores.api import admin, auth, chores, instances, members, ws
from family_chores.api.errors import DomainError
from family_chores.api.events import WSManager
from family_chores.config import Options, load_options
from family_chores.core.time import local_today
from family_chores.db.base import make_async_engine, make_session_factory
from family_chores.db.startup import BootstrapResult, bootstrap_db
from family_chores.ha import HABridge, NoOpBridge, make_client_from_env
from family_chores.ha.client import HAClientError
from family_chores.ha.reconcile import reconcile_once
from family_chores.scheduler import make_scheduler
from family_chores.security import ensure_jwt_secret
from family_chores.services.rollover_service import run_rollover

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

_SKIP_SCHEDULER_ENV = "FAMILY_CHORES_SKIP_SCHEDULER"


async def _resolve_effective_timezone(
    opts: Options, client: object | None
) -> str:
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


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    opts = cast(Options, app.state.options)

    app.state.bootstrap = bootstrap_db(opts.db_path, opts.db_backup_path)
    app.state.engine = make_async_engine(opts.db_path)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.ws_manager = WSManager()

    async with app.state.session_factory() as session:
        app.state.jwt_secret = await ensure_jwt_secret(session)

    ha_client = make_client_from_env()
    app.state.ha_client = ha_client
    tz = await _resolve_effective_timezone(opts, ha_client)
    app.state.effective_timezone = tz

    if ha_client is None:
        app.state.bridge = NoOpBridge()
    else:
        app.state.bridge = HABridge(ha_client, app.state.session_factory)
    await app.state.bridge.start()

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


def _bootstrap_payload(app: FastAPI) -> dict[str, str | None] | None:
    result: BootstrapResult | None = getattr(app.state, "bootstrap", None)
    if result is None:
        return None
    return {"action": result.action, "banner": result.banner}


def _error_payload(error: str, detail: str, request_id: str) -> dict[str, str]:
    return {"error": error, "detail": detail, "request_id": request_id}


def _install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(exc.error_code, exc.detail, rid),
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        code = _status_code_to_error_code(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, str(exc.detail), rid),
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "detail": "request body or params failed validation",
                # jsonable_encoder strips non-JSON types (ValueError, bytes,
                # etc.) that Pydantic v2 sometimes puts in `ctx`.
                "errors": jsonable_encoder(exc.errors()),
                "request_id": rid,
            },
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "unknown")
        log.exception("unhandled error [req=%s]: %s", rid, exc)
        return JSONResponse(
            status_code=500,
            content=_error_payload("internal_error", "internal server error", rid),
            headers={"X-Request-ID": rid},
        )


def _status_code_to_error_code(status: int) -> str:
    return {
        400: "bad_request",
        401: "auth_required",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "validation_error",
    }.get(status, "http_error")


def _install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _with_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID") or secrets.token_hex(6)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


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

    _install_request_id_middleware(app)
    _install_exception_handlers(app)

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
            "timezone": getattr(app.state, "effective_timezone", opts.effective_timezone),
            "ha_connected": getattr(app.state, "ha_client", None) is not None,
            "bootstrap": _bootstrap_payload(app),
        }

    app.include_router(auth.router)
    app.include_router(members.router)
    app.include_router(chores.router)
    app.include_router(instances.router)
    app.include_router(admin.router)
    app.include_router(ws.router)

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
