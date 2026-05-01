"""HA implementation of the `CalendarProvider` Protocol (DECISIONS §14).

Wraps `HAClient.call_service("calendar", "get_events", ...)` and parses
the response into the provider-agnostic `RawEvent` shape that the
service layer composes with the cache + prep parser.

Per-entity error handling:
  - HA reports per-calendar errors by omitting that entity from the
    `service_response` block. We treat "asked for X, no key for X in
    response" as unreachable.
  - All-or-nothing transport errors (HAUnavailableError, HAServerError,
    HAUnauthorizedError) mark every requested entity as unreachable so
    the kid view degrades to the empty state rather than crashing.
  - Other HAClientError (4xx misc) is also surfaced as unreachable —
    a 400 because of a malformed entity_id shouldn't take down the
    monthly view.

Recurrences: HA expands them server-side within the requested window
(DECISIONS §14 Q8) so we don't have to deal with RRULE here. Each
expanded occurrence comes back as its own event.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from family_chores_api.services.calendar.provider import (
    CalendarProvider,
    CalendarProviderResult,
    RawEvent,
)

from family_chores_addon.ha.client import HAClient, HAClientError

log = logging.getLogger(__name__)


class HACalendarProvider(CalendarProvider):
    """Reads `calendar.*` entities via HA's REST API.

    The addon constructs one of these per request lifetime (cheap — it
    just holds a reference to the shared HAClient).
    """

    def __init__(self, client: HAClient) -> None:
        self._client = client

    async def get_events(
        self,
        entity_ids: list[str],
        from_dt: datetime,
        to_dt: datetime,
    ) -> CalendarProviderResult:
        if not entity_ids:
            return CalendarProviderResult()

        payload: dict[str, Any] = {
            "entity_id": list(entity_ids),
            "start_date_time": _format_for_ha(from_dt),
            "end_date_time": _format_for_ha(to_dt),
        }

        try:
            response = await self._client.call_service(
                "calendar",
                "get_events",
                payload,
                return_response=True,
            )
        except HAClientError as exc:
            # All-or-nothing transport / auth / 5xx — every requested
            # entity becomes unreachable. The kid view falls back to
            # the empty state with a per-tile "couldn't reach" hint.
            log.warning("calendar.get_events failed: %s", exc)
            return CalendarProviderResult(unreachable=list(entity_ids))

        return _parse_response(response, entity_ids)


def _format_for_ha(when: datetime) -> str:
    """HA's calendar.get_events accepts ISO 8601 with offset.

    A naive datetime is interpreted as UTC (matches the rest of the
    codebase's tz handling) so the bridge doesn't silently shift
    a local-time window into the wrong day.
    """
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.isoformat()


def _parse_response(
    response: Any, requested_ids: list[str]
) -> CalendarProviderResult:
    """Pull a flat `RawEvent` list out of HA's `service_response` block.

    Defensive across the response shape — every level can be missing
    or wrong type if the upstream changed (or if a fake returns a
    different shape in tests).
    """
    service_block = (response or {}).get("service_response") or {}
    if not isinstance(service_block, dict):
        # Whole shape is wrong — bail out as if everything was unreachable.
        log.warning("calendar.get_events returned unexpected shape: %r", response)
        return CalendarProviderResult(unreachable=list(requested_ids))

    events: list[RawEvent] = []
    unreachable: list[str] = []

    for entity_id in requested_ids:
        entity_block = service_block.get(entity_id)
        if entity_block is None:
            # HA dropped this entity from the response — treat as
            # unreachable rather than "no events" so the parent sees
            # a real signal that something's wrong.
            unreachable.append(entity_id)
            continue
        if not isinstance(entity_block, dict):
            unreachable.append(entity_id)
            continue

        items = entity_block.get("events") or []
        if not isinstance(items, list):
            unreachable.append(entity_id)
            continue

        for raw in items:
            event = _parse_event(entity_id, raw)
            if event is not None:
                events.append(event)

    return CalendarProviderResult(events=events, unreachable=unreachable)


def _parse_event(entity_id: str, raw: Any) -> RawEvent | None:
    """Convert one HA event dict → `RawEvent`. Returns None on garbage
    inputs rather than raising — one bad event shouldn't drop the
    whole calendar.
    """
    if not isinstance(raw, dict):
        return None

    summary = str(raw.get("summary") or "").strip()
    if not summary:
        # Calendar feeds without a title are useless to display.
        return None

    raw_start = raw.get("start")
    raw_end = raw.get("end")
    if not isinstance(raw_start, str) or not isinstance(raw_end, str):
        return None

    parsed = _parse_start_end(raw_start, raw_end)
    if parsed is None:
        return None
    start, end, all_day = parsed

    description = raw.get("description")
    location = raw.get("location")
    return RawEvent(
        entity_id=entity_id,
        summary=summary,
        description=str(description) if isinstance(description, str) else None,
        start=start,
        end=end,
        all_day=all_day,
        location=str(location) if isinstance(location, str) else None,
    )


def _parse_start_end(
    raw_start: str, raw_end: str
) -> tuple[datetime, datetime, bool] | None:
    """Decode the HA date / datetime quirk.

    HA returns a date-only string (`"2026-05-01"`) for all-day events
    and an ISO 8601 datetime (`"2026-05-01T16:00:00-07:00"`) for timed
    ones. We normalise both to tz-aware datetimes:
      - all-day → midnight UTC on each side, `all_day=True`
      - timed → `fromisoformat`, naive treated as UTC.
    """
    try:
        start_dt, start_all_day = _parse_iso_value(raw_start)
        end_dt, end_all_day = _parse_iso_value(raw_end)
    except ValueError:
        return None

    # Both ends should agree on all-day vs timed. If they disagree
    # (shouldn't happen but defend), trust the start.
    all_day = start_all_day
    return start_dt, end_dt, all_day


def _parse_iso_value(value: str) -> tuple[datetime, bool]:
    """Parse a string that's either `YYYY-MM-DD` or an ISO 8601 datetime.

    Returns `(dt, is_date_only)`. Raises ValueError on garbage.
    """
    if "T" not in value:
        # Date-only.
        d = date.fromisoformat(value)
        return datetime(d.year, d.month, d.day, tzinfo=UTC), True
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt, False
