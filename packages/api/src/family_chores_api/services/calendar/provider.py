"""`CalendarProvider` Protocol + raw event shape (DECISIONS §14).

The Protocol is the abstraction seam between the service layer
(provider-agnostic event composition + prep parsing + caching) and the
deployment-specific calendar source (HA entities for the addon, future
CalDAV/Google API for standalone deployments).

The shape returned by providers is intentionally minimal — `RawEvent`
carries only what every backend has (summary, description, start, end,
all-day flag, location). The richer API-layer `CalendarEvent` (with
prep items, member attribution, etc.) is composed in `service.py`.

`CalendarProviderResult` separates `events` from `unreachable` so the
service layer can render a per-entity error state ("couldn't reach
calendar X") instead of either silently dropping the entity or
failing the whole request — DECISIONS §14 Q11.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RawEvent:
    """Provider-agnostic event payload.

    `start` and `end` are timezone-aware datetimes. `all_day` is true
    for date-only events (e.g. "Spring Break" running 9am Apr 7 to
    9am Apr 14). When `all_day` is True the start/end are still
    datetimes (midnight in the local tz) so callers don't need a
    type-discriminated union.
    """

    entity_id: str
    summary: str
    description: str | None
    start: datetime
    end: datetime
    all_day: bool
    location: str | None = None


@dataclass(slots=True)
class CalendarProviderResult:
    """Aggregate result of a `get_events` call.

    `events` is the flat list across all requested entity IDs;
    `unreachable` is the subset of entity IDs that failed to fetch
    (network error, HA returned 5xx for that entity, etc.). Callers
    surface `unreachable` to the UI so a missing-calendar state can
    render per-tile.
    """

    events: list[RawEvent] = field(default_factory=list)
    unreachable: list[str] = field(default_factory=list)


class CalendarProviderError(Exception):
    """Base for any failure inside a provider implementation.

    Providers should catch upstream errors (HAClientError, httpx
    failures, CalDAV exceptions) and either:
      - raise `CalendarProviderError` for unrecoverable errors that
        should fail the whole request (provider misconfigured, etc.)
      - swallow and add the entity_id to `result.unreachable` for
        per-entity errors (one calendar offline, others fine)
    """


class CalendarProvider(Protocol):
    """The contract every deployment target's calendar source implements.

    `get_events` is the only method — `from_dt` and `to_dt` bound the
    query window (provider expands recurrences in this window;
    DECISIONS §14 Q8). Returning `CalendarProviderResult` rather than
    `list[RawEvent]` lets the implementation report per-entity errors
    without losing data from the entities that succeeded.
    """

    async def get_events(
        self,
        entity_ids: list[str],
        from_dt: datetime,
        to_dt: datetime,
    ) -> CalendarProviderResult: ...


class NoOpCalendarProvider(CalendarProvider):
    """Stand-in for deployments without a calendar backend.

    Always returns an empty result with no events and nothing
    unreachable. Used by:
      - The addon when no HA credentials are present (NoOpBridge path).
      - The standalone SaaS target until a CalDAV / Google Calendar
        provider is added in Tier 2 (DECISIONS §14 roadmap).
      - Tests that only need the calendar service shape, not real data.
    """

    async def get_events(
        self,
        entity_ids: list[str],
        from_dt: datetime,
        to_dt: datetime,
    ) -> CalendarProviderResult:
        return CalendarProviderResult()
