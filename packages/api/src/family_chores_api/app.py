"""FastAPI application factory for Family Chores.

Deployment-target-agnostic: builds a FastAPI app with all routers, error
handlers, request-ID middleware, and a `/api/health` endpoint, but is
*not* aware of:
- the SPA static dir (each deployment target serves its own SPA, or none);
- the `/api/info` payload (the add-on's `ha_connected` / bootstrap
  banner / options snapshot don't apply to other targets);
- the lifespan (each deployment target wires its own collaborators —
  session factory, HA bridge, WS manager, JWT secret, effective_timezone,
  week_starts_on — onto `app.state` from its own lifespan).

The caller passes the `lifespan` factory and adds any deployment-specific
routes / static mounts to the returned app **before** mounting `StaticFiles`
at `/` (the static mount swallows the root and must come last).

See `family_chores.app.create_app` for the add-on's wrapper, and
`apps/saas-backend/src/family_chores_saas/app_factory.py` (Phase 3) for
the future SaaS wrapper.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from family_chores_api.errors import DomainError
from family_chores_api.routers import (
    admin,
    auth,
    chores,
    instances,
    members,
    rewards,
    suggestions,
    ws,
)

log = logging.getLogger(__name__)

LifespanFactory = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def _error_payload(error: str, detail: str, request_id: str) -> dict[str, str]:
    return {"error": error, "detail": detail, "request_id": request_id}


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


def _install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _with_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("X-Request-ID") or secrets.token_hex(6)
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


def create_app(
    *,
    title: str = "Family Chores",
    version: str = "0.0.0",
    docs_url: str | None = "/api/docs",
    redoc_url: str | None = None,
    openapi_url: str | None = "/api/openapi.json",
    lifespan: LifespanFactory | None = None,
) -> FastAPI:
    """Build a FastAPI app with routers + middleware + error handlers.

    Caller responsibilities:

    - Provide a `lifespan` that wires `app.state.{session_factory, bridge,
      ws_manager, jwt_secret, effective_timezone, week_starts_on}` before
      requests are served. The deps in `family_chores_api.deps` read from
      these `app.state` slots.
    - Add deployment-specific routes (e.g. `/api/info`) on the returned
      app **before** mounting any catch-all StaticFiles at `/`.
    """
    app = FastAPI(
        title=title,
        version=version,
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )

    _install_request_id_middleware(app)
    _install_exception_handlers(app)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": version}

    app.include_router(auth.router)
    app.include_router(members.router)
    app.include_router(chores.router)
    app.include_router(instances.router)
    app.include_router(admin.router)
    app.include_router(suggestions.router)
    app.include_router(rewards.rewards_router)
    app.include_router(rewards.redemptions_router)
    app.include_router(rewards.member_redemptions_router)
    app.include_router(ws.router)

    return app
