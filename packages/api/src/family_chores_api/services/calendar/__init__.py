"""Calendar integration service layer (DECISIONS §14).

Three pieces:

  - `provider.py` — `CalendarProvider` Protocol that any deployment
    target's calendar source plugs into. The addon ships
    `HACalendarProvider` (reads from HA `calendar.*` entities); a
    future SaaS deployment would write a CalDAV / Google Calendar
    provider against the same Protocol.

  - `prep.py` — pure prep-text parsing. Two passes (explicit
    `[prep: ...]` tag, then verb-detection fallback) feed a single
    `list[PrepItem]` payload server-side.

  - `cache.py` — 60-second TTL by `(entity_id, day)` with manual
    invalidation API. The TTL is short enough that "I just added an
    event" usually shows up by the next kid glance; the manual
    invalidation backs the parent's explicit Refresh button on the
    monthly view.

  - `service.py` — composition. `get_events_for_window` orchestrates
    cache + provider + prep parsing into the API-layer `CalendarEvent`
    shape that routers serialise.
"""

from family_chores_api.services.calendar.cache import CalendarCache
from family_chores_api.services.calendar.prep import PrepItem, extract_prep_items
from family_chores_api.services.calendar.provider import (
    CalendarProvider,
    CalendarProviderError,
    CalendarProviderResult,
    NoOpCalendarProvider,
    RawEvent,
)
from family_chores_api.services.calendar.service import (
    CalendarEvent,
    CalendarWindow,
    get_events_for_window,
    hide_past,
    partition_by_member,
)

__all__ = [
    "CalendarCache",
    "CalendarEvent",
    "CalendarProvider",
    "CalendarProviderError",
    "CalendarProviderResult",
    "CalendarWindow",
    "NoOpCalendarProvider",
    "PrepItem",
    "RawEvent",
    "extract_prep_items",
    "get_events_for_window",
    "hide_past",
    "partition_by_member",
]
