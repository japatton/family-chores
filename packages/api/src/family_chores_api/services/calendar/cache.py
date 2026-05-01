"""60-second TTL cache for calendar events (DECISIONS §14 Q10).

Keyed by `(entity_id, day)`. The day-level slicing keeps the cache
warm for monthly-view scrolls (each visible day is its own key) while
still letting the parent's "I just added an event today" scenario
recover within 60 seconds.

Manual invalidation backs:
  - `POST /api/calendar/refresh` (parent's explicit refresh button)
  - household-settings or member-calendar-mapping changes (config
    edits should be visible immediately)

Single-process / in-memory. The addon runs as a single uvicorn worker
so no cross-worker coordination is needed. A future SaaS deployment
that scales horizontally would swap this for Redis or similar against
the same Protocol if needed; the call sites only depend on `get` /
`put` / `invalidate`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC
from datetime import date as date_type
from datetime import datetime, timedelta

from family_chores_api.services.calendar.provider import RawEvent


@dataclass(slots=True)
class _CacheEntry:
    events: list[RawEvent]
    expires_at: datetime


_DEFAULT_TTL_SECONDS = 60.0


class CalendarCache:
    """Thread-safe (asyncio-lock-protected) TTL cache by `(entity_id, day)`."""

    def __init__(self, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._store: dict[tuple[str, date_type], _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def get(
        self, entity_id: str, day: date_type, *, now: datetime | None = None
    ) -> list[RawEvent] | None:
        """Return cached events for this `(entity_id, day)`, or None on
        miss / expiry. Expired entries are evicted on access (no
        background sweeper)."""
        when = now if now is not None else datetime.now(UTC)
        key = (entity_id, day)
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at <= when:
                # Stale — evict and report miss.
                del self._store[key]
                return None
            return list(entry.events)

    async def put(
        self,
        entity_id: str,
        day: date_type,
        events: list[RawEvent],
        *,
        now: datetime | None = None,
    ) -> None:
        when = now if now is not None else datetime.now(UTC)
        async with self._lock:
            self._store[(entity_id, day)] = _CacheEntry(
                events=list(events), expires_at=when + self._ttl
            )

    async def invalidate(self, entity_id: str | None = None) -> int:
        """Drop entries matching `entity_id`, or all entries when None.

        Returns the number of entries dropped. Used by:
          - `POST /api/calendar/refresh` (passes None → drop all)
          - household-settings / member-calendar-mapping mutations
            (passes None → drop all; the surface area of changes is
            small enough that a full bust is simpler than tracking
            which entities a config change affected)
        """
        async with self._lock:
            if entity_id is None:
                count = len(self._store)
                self._store.clear()
                return count
            keys = [k for k in self._store if k[0] == entity_id]
            for k in keys:
                del self._store[k]
            return len(keys)

    async def size(self, *, now: datetime | None = None) -> int:
        """Live entry count (after expiry sweep — useful for tests).

        `now` is injectable for the same reason `get` / `put` accept it:
        deterministic expiry behaviour without sleep-driven tests.
        """
        when = now if now is not None else datetime.now(UTC)
        async with self._lock:
            stale = [k for k, v in self._store.items() if v.expires_at <= when]
            for k in stale:
                del self._store[k]
            return len(self._store)
