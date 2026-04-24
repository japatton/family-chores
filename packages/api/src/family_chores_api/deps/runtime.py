"""`app.state` reader deps that don't fit anywhere else.

Each of these reads a value the deployment target's lifespan put on
`app.state` and returns a default when unset (so unit tests that bypass
the full lifespan don't 500). Centralised here so the splits don't grow
a misc grab-bag.
"""

from __future__ import annotations

from typing import cast

from fastapi import Request

from family_chores_api.events import WSManager


def get_ws_manager(request: Request) -> WSManager:
    return cast(WSManager, request.app.state.ws_manager)


def get_jwt_secret(request: Request) -> str:
    return cast(str, request.app.state.jwt_secret)


def get_effective_timezone(request: Request) -> str:
    """Effective IANA tz, set by the deployment target's lifespan.

    The add-on lifespan computes this from the `timezone` option, the HA
    `/api/config → time_zone` fetch, or UTC as a final fallback (decision
    §4 #44). Routers see only the resolved string. Returns `"UTC"` if
    the lifespan didn't run (test-only path).
    """
    cached = getattr(request.app.state, "effective_timezone", None)
    if isinstance(cached, str) and cached:
        return cached
    return "UTC"


def get_week_starts_on(request: Request) -> str:
    """Configured first day of the week (`"monday"` or `"sunday"`).

    Set by the deployment target's lifespan from its options object so
    `packages/api` doesn't need to know the addon's `Options` schema.
    Defaults to `"monday"` if unset (matches addon's default in §4 #19).
    """
    cached = getattr(request.app.state, "week_starts_on", None)
    if isinstance(cached, str) and cached:
        return cached
    return "monday"
