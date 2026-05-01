"""DI shims for the calendar provider + cache (DECISIONS §14).

The provider and cache live as singletons on `app.state` (set up in
the deployment-specific lifespan — addon's `app.py` constructs an
`HACalendarProvider` from the HA client; the SaaS target wires
`NoOpCalendarProvider` until a CalDAV / Google Calendar provider
ships in Tier 2).

These accessors fail loudly if the lifespan didn't set them — that's
intentional: a missing provider would silently return empty results
and confuse the parent debugging the kid view. Better to 500 with a
clear message and a request id.
"""

from __future__ import annotations

from typing import cast

from fastapi import Request

from family_chores_api.services.calendar import (
    CalendarCache,
    CalendarProvider,
)


def get_calendar_provider(request: Request) -> CalendarProvider:
    """Return the per-app `CalendarProvider` set up by the lifespan.

    Raise RuntimeError if the slot is missing — the deployment forgot
    to wire one. (NoOpCalendarProvider is the minimum viable wiring.)
    """
    provider = getattr(request.app.state, "calendar_provider", None)
    if provider is None:
        raise RuntimeError(
            "calendar_provider not set on app.state — wire one in the lifespan"
        )
    return cast(CalendarProvider, provider)


def get_calendar_cache(request: Request) -> CalendarCache:
    """Return the per-app `CalendarCache` set up by the lifespan."""
    cache = getattr(request.app.state, "calendar_cache", None)
    if cache is None:
        raise RuntimeError(
            "calendar_cache not set on app.state — wire one in the lifespan"
        )
    return cast(CalendarCache, cache)
