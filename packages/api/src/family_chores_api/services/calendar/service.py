"""Composition: `CalendarProvider` + `CalendarCache` + prep parsing.

The public surface here is what routers consume — provider-agnostic,
cache-aware, prep-enriched. `CalendarEvent` is the API-layer shape
(`RawEvent` + parsed prep items); routers serialise it directly into
JSON via the matching Pydantic schema.

Two read paths:

  - `get_events_for_window(provider, cache, entity_ids, from_dt, to_dt)`
    — the workhorse. Handles cache lookup per `(entity_id, day)`,
    fetches misses from the provider in a single call, fills the
    cache, and merges everything into a flat sorted list.

  - `partition_by_member(events, members)` — convenience for the
    `/api/today` consumer that needs `{member_id: events}` shape.

Past-event filtering (DECISIONS §14 Q7 — hide once `event.end < now`)
is the caller's responsibility; the service returns events as-is in
the requested window so the monthly view can still display past days.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any

from family_chores_api.services.calendar.cache import CalendarCache
from family_chores_api.services.calendar.prep import PrepItem, extract_prep_items
from family_chores_api.services.calendar.provider import (
    CalendarProvider,
    RawEvent,
)


@dataclass(slots=True)
class CalendarEvent:
    """API-layer event shape — `RawEvent` enriched with parsed prep
    items. The router serialises this directly via the Pydantic schema.
    """

    entity_id: str
    summary: str
    description: str | None
    start: datetime
    end: datetime
    all_day: bool
    location: str | None
    prep_items: list[PrepItem]

    @classmethod
    def from_raw(cls, raw: RawEvent) -> CalendarEvent:
        return cls(
            entity_id=raw.entity_id,
            summary=raw.summary,
            description=raw.description,
            start=raw.start,
            end=raw.end,
            all_day=raw.all_day,
            location=raw.location,
            prep_items=extract_prep_items(raw.description),
        )


@dataclass(slots=True)
class CalendarWindow:
    """Result of a windowed event query. Carries both the events and the
    list of entity IDs that couldn't be reached this fetch — the router
    surfaces `unreachable` so the UI can show a per-tile error state."""

    events: list[CalendarEvent] = field(default_factory=list)
    unreachable: list[str] = field(default_factory=list)


def _days_in_window(from_dt: datetime, to_dt: datetime) -> list[date_type]:
    """Inclusive day range (UTC date boundaries). Used as the cache-key
    iteration set."""
    start_day = from_dt.date()
    end_day = to_dt.date()
    days: list[date_type] = []
    d = start_day
    while d <= end_day:
        days.append(d)
        d += timedelta(days=1)
    return days


async def get_events_for_window(
    provider: CalendarProvider,
    cache: CalendarCache,
    entity_ids: list[str],
    from_dt: datetime,
    to_dt: datetime,
) -> CalendarWindow:
    """Fetch events for the window, using the cache where possible.

    Strategy:
      - For each (entity_id, day) cell in the requested window, check
        the cache.
      - Anything missing → batched provider call for those (entity_id,
        day) pairs (collapsed by entity_id with a single from/to span).
      - Cache misses are filled and the union of cached + freshly
        fetched events is returned.
      - `unreachable` from the provider call propagates straight through.
    """
    if not entity_ids:
        return CalendarWindow()

    days = _days_in_window(from_dt, to_dt)
    if not days:
        return CalendarWindow()

    # Collect cache hits + identify which entity_ids need a provider
    # call. We don't try to slice the provider call by partial-day —
    # if any day is missing for an entity, fetch the whole window for
    # that entity and re-cache by day.
    cached: dict[tuple[str, date_type], list[RawEvent]] = {}
    missing_entities: set[str] = set()
    for entity_id in entity_ids:
        for day in days:
            hit = await cache.get(entity_id, day)
            if hit is not None:
                cached[(entity_id, day)] = hit
            else:
                missing_entities.add(entity_id)

    fresh = await _fetch_and_cache(
        provider, cache, list(missing_entities), from_dt, to_dt, days
    )

    # Union: cached + fresh. Fresh overrides cached for any (entity, day)
    # the provider just refreshed.
    by_key: dict[tuple[str, date_type], list[RawEvent]] = dict(cached)
    by_key.update(fresh.by_key)

    all_events: list[RawEvent] = [
        event for events in by_key.values() for event in events
    ]
    all_events.sort(key=lambda e: (e.start, e.entity_id, e.summary))
    return CalendarWindow(
        events=[CalendarEvent.from_raw(e) for e in all_events],
        unreachable=fresh.unreachable,
    )


@dataclass(slots=True)
class _FreshFetchResult:
    by_key: dict[tuple[str, date_type], list[RawEvent]]
    unreachable: list[str]


async def _fetch_and_cache(
    provider: CalendarProvider,
    cache: CalendarCache,
    entity_ids: list[str],
    from_dt: datetime,
    to_dt: datetime,
    days: list[date_type],
) -> _FreshFetchResult:
    if not entity_ids:
        return _FreshFetchResult(by_key={}, unreachable=[])

    result = await provider.get_events(entity_ids, from_dt, to_dt)

    # Bucket the returned events by (entity_id, day-of-start).
    buckets: dict[tuple[str, date_type], list[RawEvent]] = {}
    for event in result.events:
        key = (event.entity_id, event.start.date())
        buckets.setdefault(key, []).append(event)

    # Fill the cache for every (entity_id, day) we asked about. Entries
    # with no events still get cached (empty list) so we don't re-query
    # for an entity that's just empty for that day.
    fetched_entities = {e for e in entity_ids if e not in result.unreachable}
    for entity_id in fetched_entities:
        for day in days:
            events = buckets.get((entity_id, day), [])
            await cache.put(entity_id, day, events)

    return _FreshFetchResult(by_key=buckets, unreachable=list(result.unreachable))


def partition_by_member(
    events: list[CalendarEvent],
    member_calendar_map: dict[int, list[str]],
) -> dict[int, list[CalendarEvent]]:
    """Group events by the member that owns each event's entity_id.

    `member_calendar_map`: `{member_id: [entity_id, ...]}` — the same
    JSON column on `members.calendar_entity_ids`. An event whose
    `entity_id` matches multiple members appears under each (this
    happens for the household-shared calendar — caller can dedupe by
    not including the shared entity in any individual member's list,
    or by treating shared events as a separate top-level set).
    """
    out: dict[int, list[CalendarEvent]] = {mid: [] for mid in member_calendar_map}
    for event in events:
        for member_id, entity_ids in member_calendar_map.items():
            if event.entity_id in entity_ids:
                out[member_id].append(event)
    return out


def hide_past(
    events: list[CalendarEvent], *, now: datetime | None = None
) -> list[CalendarEvent]:
    """Filter out events whose `end` is in the past (DECISIONS §14 Q7).

    `now` injectable for testability. Naive `now` is treated as UTC so
    callers can pass either flavour without worrying about tz mismatches
    against provider-supplied (tz-aware) event end times.
    """
    when = now if now is not None else datetime.now(UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    out: list[CalendarEvent] = []
    for event in events:
        end = event.end
        # Normalise the comparison side: a provider-supplied naive end
        # gets treated as UTC too. In practice `RawEvent.end` should
        # always be tz-aware (per the provider contract), but we don't
        # want a malformed feed to crash the kid view.
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        if end >= when:
            out.append(event)
    return out


def _summarise_for_log(window: CalendarWindow) -> dict[str, Any]:
    """Small helper used by callers that want to log the result shape
    without dumping every event."""
    return {
        "events": len(window.events),
        "unreachable": window.unreachable,
    }
