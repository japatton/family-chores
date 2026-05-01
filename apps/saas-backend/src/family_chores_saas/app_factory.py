"""SaaS-backend FastAPI app factory — Phase 3 placeholder.

The SaaS deployment target's only job (today) is to prove that
`family_chores_api.create_app` composes cleanly with a non-add-on
identity strategy. Phase 3 will replace this scaffold with:

  - A real `AuthStrategy` that verifies JWTs from a managed identity
    provider (Supabase / Clerk / WorkOS / etc.) and resolves to a
    real `Identity.household_id`.
  - A managed Postgres engine (not SQLite) and per-request session
    factory.
  - A real bridge — probably a no-op there too, since the SaaS doesn't
    push state into HA. The protocol stays the same so the routers are
    identical.
  - Observability (OpenTelemetry traces, structured logs, metrics).
  - Auth-rate-limiting + IP allow-listing on `/api/auth/*`.

Until then: every tenant-scoped endpoint returns 501 because the
`PlaceholderAuthStrategy` raises during dep resolution. `/api/health`
stays at 200 — it doesn't depend on the auth strategy.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status

from family_chores_api import WSManager, create_app as create_api_app
from family_chores_api.bridge import BridgeProtocol
from family_chores_api.services.calendar import (
    CalendarCache,
    NoOpCalendarProvider,
)
from family_chores_saas import __version__
from family_chores_saas.auth import PlaceholderAuthStrategy


class _NoOpBridge(BridgeProtocol):
    """Bridge stand-in for the SaaS scaffold.

    The SaaS doesn't talk to HA, so a no-op satisfies the protocol the
    routers depend on. Inlined here rather than imported from the addon
    so this scaffold has no `family_chores_addon.*` dependency (apps
    don't import other apps). Will likely move to `packages/api/bridge.py`
    in a future cleanup if a third deployment target appears.
    """

    def notify_member_dirty(self, member_id: int) -> None:  # pragma: no cover
        pass

    def notify_approvals_dirty(self) -> None:  # pragma: no cover
        pass

    def notify_instance_changed(self, instance_id: int) -> None:  # pragma: no cover
        pass

    def enqueue_event(self, event_type: str, payload: dict[str, Any]) -> None:  # pragma: no cover
        pass

    async def force_flush(self) -> None:  # pragma: no cover
        pass

    async def start(self) -> None:  # pragma: no cover
        pass

    async def stop(self) -> None:  # pragma: no cover
        pass


_SAAS_NOT_IMPLEMENTED = "SaaS deployment is a Phase 3 placeholder — see DECISIONS §11."


def _raise_501(*args: Any, **kwargs: Any) -> Any:
    """Stand-in for app.state.session_factory.

    FastAPI resolves a route's deps roughly in parallel — there's no
    guarantee `get_current_household_id` (which routes through
    `PlaceholderAuthStrategy.identify` → 501) runs before
    `get_session` (which calls this factory). Raising HTTPException(501)
    here makes the response 501 regardless of which dep wins the race.

    Step-12 work will replace this with a real Postgres session factory.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=_SAAS_NOT_IMPLEMENTED,
    )


def _build_lifespan() -> Any:
    """The SaaS lifespan installs the placeholder strategy + bridge plus
    just enough `app.state` to keep `family_chores_api.deps` resolvable.

    Real values (Postgres engine + session factory, observability hooks,
    JWT secret from env) land in Phase 3. The values seeded here exist
    only so dep resolution doesn't AttributeError; tenant-scoped routes
    still 501 because either `PlaceholderAuthStrategy.identify` or the
    `_raise_501` session-factory stub bubbles up first.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.auth_strategy = PlaceholderAuthStrategy()
        app.state.bridge = _NoOpBridge()
        app.state.ws_manager = WSManager()
        app.state.session_factory = _raise_501
        app.state.jwt_secret = "saas-placeholder-secret-not-for-use"
        app.state.effective_timezone = "UTC"
        app.state.week_starts_on = "monday"
        # Calendar shims (DECISIONS §14). Tier 2 swaps the no-op for a
        # CalDAV / Google Calendar provider; for now the SaaS scaffold
        # just gives the routes something resolvable so the OpenAPI
        # schema renders and the calendar router doesn't 500 at import.
        app.state.calendar_cache = CalendarCache()
        app.state.calendar_provider = NoOpCalendarProvider()
        yield

    return _lifespan


def create_app() -> FastAPI:
    """Build the SaaS FastAPI app (placeholder; Phase 3 replaces this)."""
    return create_api_app(
        title="Family Chores (SaaS placeholder)",
        version=__version__,
        lifespan=_build_lifespan(),
    )
