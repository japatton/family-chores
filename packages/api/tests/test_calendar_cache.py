"""Tests for `CalendarCache` — TTL behaviour, eviction, invalidation.

The cache is a small piece (60s TTL keyed by `(entity_id, day)`) but it
sits on the hot read path so the contract matters: stale entries don't
leak, manual invalidation works at both the all-entities and
single-entity granularity, and concurrent access through the asyncio
lock doesn't drop entries.

Time is injected via the `now` kwarg on `get` / `put` so tests don't
need `freezegun` or sleeps — the cache is a pure function of `(now,
prior puts)`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from family_chores_api.services.calendar.cache import CalendarCache
from family_chores_api.services.calendar.provider import RawEvent


def _event(entity_id: str, summary: str = "Soccer") -> RawEvent:
    """Tiny builder so tests stay readable. Datetimes are naive UTC —
    the cache doesn't care; it's the caller's job to keep them
    consistent."""
    return RawEvent(
        entity_id=entity_id,
        summary=summary,
        description=None,
        start=datetime(2026, 5, 1, 16, 0),
        end=datetime(2026, 5, 1, 17, 0),
        all_day=False,
    )


# ─── miss / hit basics ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_miss_returns_none():
    cache = CalendarCache()
    assert await cache.get("calendar.kid", date(2026, 5, 1)) is None


@pytest.mark.asyncio
async def test_put_then_get_returns_events():
    cache = CalendarCache()
    events = [_event("calendar.kid")]
    await cache.put("calendar.kid", date(2026, 5, 1), events)
    hit = await cache.get("calendar.kid", date(2026, 5, 1))
    assert hit == events


@pytest.mark.asyncio
async def test_get_returns_independent_copy():
    """The list returned from `get` is a copy — caller mutating it must
    not affect a subsequent `get`."""
    cache = CalendarCache()
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")])
    first = await cache.get("calendar.kid", date(2026, 5, 1))
    assert first is not None
    first.append(_event("calendar.kid", summary="injected"))
    second = await cache.get("calendar.kid", date(2026, 5, 1))
    assert second is not None
    assert len(second) == 1
    assert second[0].summary == "Soccer"


@pytest.mark.asyncio
async def test_put_stores_independent_copy():
    """A caller mutating the input list after `put` must not change
    what `get` returns."""
    cache = CalendarCache()
    inputs = [_event("calendar.kid")]
    await cache.put("calendar.kid", date(2026, 5, 1), inputs)
    inputs.append(_event("calendar.kid", summary="injected after put"))
    hit = await cache.get("calendar.kid", date(2026, 5, 1))
    assert hit is not None
    assert len(hit) == 1
    assert hit[0].summary == "Soccer"


@pytest.mark.asyncio
async def test_empty_list_is_a_valid_cached_value():
    """Providers with no events for a day still cache an empty list so
    we don't re-query. Empty != miss."""
    cache = CalendarCache()
    await cache.put("calendar.kid", date(2026, 5, 1), [])
    hit = await cache.get("calendar.kid", date(2026, 5, 1))
    assert hit == []


# ─── TTL & expiry ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_returns_none_after_ttl_expires():
    cache = CalendarCache(ttl_seconds=60)
    t0 = datetime(2026, 5, 1, 12, 0, 0)
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")], now=t0)
    # Within TTL — hit.
    assert await cache.get("calendar.kid", date(2026, 5, 1), now=t0 + timedelta(seconds=59)) is not None
    # Past TTL — miss (boundary is `<=` so equal-to-expiry is also a miss).
    assert await cache.get("calendar.kid", date(2026, 5, 1), now=t0 + timedelta(seconds=60)) is None
    assert await cache.get("calendar.kid", date(2026, 5, 1), now=t0 + timedelta(seconds=61)) is None


@pytest.mark.asyncio
async def test_expired_entry_is_evicted_on_access():
    """Stale entries should be removed from the store when read, not
    accumulate until the next sweep."""
    cache = CalendarCache(ttl_seconds=60)
    t0 = datetime(2026, 5, 1, 12, 0, 0)
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")], now=t0)
    assert await cache.size(now=t0) == 1
    # Trigger expiry via `get` past the TTL.
    assert (
        await cache.get(
            "calendar.kid", date(2026, 5, 1), now=t0 + timedelta(seconds=120)
        )
        is None
    )
    # Size should reflect the eviction (no need for an explicit sweep).
    # Pass a `now` past the TTL so sweep behaviour is deterministic.
    assert await cache.size(now=t0 + timedelta(seconds=120)) == 0


@pytest.mark.asyncio
async def test_put_refreshes_ttl():
    """A second put for the same key resets the TTL."""
    cache = CalendarCache(ttl_seconds=60)
    t0 = datetime(2026, 5, 1, 12, 0, 0)
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")], now=t0)
    # Re-put at t0 + 50s.
    await cache.put(
        "calendar.kid",
        date(2026, 5, 1),
        [_event("calendar.kid", summary="updated")],
        now=t0 + timedelta(seconds=50),
    )
    # Original would have expired by now, but the refresh keeps it alive.
    hit = await cache.get(
        "calendar.kid", date(2026, 5, 1), now=t0 + timedelta(seconds=100)
    )
    assert hit is not None
    assert hit[0].summary == "updated"


@pytest.mark.asyncio
async def test_custom_ttl_seconds():
    """Constructor TTL is honoured (used by tests that need short windows)."""
    cache = CalendarCache(ttl_seconds=5)
    t0 = datetime(2026, 5, 1, 12, 0, 0)
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")], now=t0)
    assert await cache.get("calendar.kid", date(2026, 5, 1), now=t0 + timedelta(seconds=4)) is not None
    assert await cache.get("calendar.kid", date(2026, 5, 1), now=t0 + timedelta(seconds=5)) is None


# ─── key independence ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_keys_are_per_entity_and_per_day():
    """Different `(entity_id, day)` pairs are independent — no
    cross-contamination."""
    cache = CalendarCache()
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid", summary="A")])
    await cache.put("calendar.kid", date(2026, 5, 2), [_event("calendar.kid", summary="B")])
    await cache.put(
        "calendar.shared", date(2026, 5, 1), [_event("calendar.shared", summary="C")]
    )

    a = await cache.get("calendar.kid", date(2026, 5, 1))
    b = await cache.get("calendar.kid", date(2026, 5, 2))
    c = await cache.get("calendar.shared", date(2026, 5, 1))

    assert a is not None and a[0].summary == "A"
    assert b is not None and b[0].summary == "B"
    assert c is not None and c[0].summary == "C"
    # An unrelated key is still a miss.
    assert await cache.get("calendar.shared", date(2026, 5, 2)) is None


# ─── invalidate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_all_drops_everything():
    cache = CalendarCache()
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")])
    await cache.put("calendar.shared", date(2026, 5, 1), [_event("calendar.shared")])
    dropped = await cache.invalidate()
    assert dropped == 2
    assert await cache.get("calendar.kid", date(2026, 5, 1)) is None
    assert await cache.get("calendar.shared", date(2026, 5, 1)) is None


@pytest.mark.asyncio
async def test_invalidate_by_entity_drops_only_that_entity():
    cache = CalendarCache()
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")])
    await cache.put("calendar.kid", date(2026, 5, 2), [_event("calendar.kid")])
    await cache.put("calendar.shared", date(2026, 5, 1), [_event("calendar.shared")])

    dropped = await cache.invalidate("calendar.kid")
    assert dropped == 2

    # Kid entries gone, shared survives.
    assert await cache.get("calendar.kid", date(2026, 5, 1)) is None
    assert await cache.get("calendar.kid", date(2026, 5, 2)) is None
    shared = await cache.get("calendar.shared", date(2026, 5, 1))
    assert shared is not None


@pytest.mark.asyncio
async def test_invalidate_unknown_entity_returns_zero():
    cache = CalendarCache()
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")])
    assert await cache.invalidate("calendar.nonexistent") == 0
    # Existing entry unaffected.
    assert await cache.get("calendar.kid", date(2026, 5, 1)) is not None


@pytest.mark.asyncio
async def test_invalidate_empty_cache_returns_zero():
    cache = CalendarCache()
    assert await cache.invalidate() == 0
    assert await cache.invalidate("calendar.anything") == 0


# ─── size ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_size_starts_zero():
    cache = CalendarCache()
    assert await cache.size() == 0


@pytest.mark.asyncio
async def test_size_counts_live_entries_and_sweeps_stale():
    """`size()` runs an expiry sweep so stale entries don't show up."""
    cache = CalendarCache(ttl_seconds=60)
    t0 = datetime(2026, 5, 1, 12, 0, 0)
    await cache.put("calendar.kid", date(2026, 5, 1), [_event("calendar.kid")], now=t0)
    await cache.put("calendar.kid", date(2026, 5, 2), [_event("calendar.kid")], now=t0)
    assert await cache.size(now=t0) == 2

    # Add a fresh entry in the future; the older two have now expired.
    t1 = t0 + timedelta(seconds=120)
    await cache.put(
        "calendar.shared", date(2026, 5, 1), [_event("calendar.shared")], now=t1
    )
    # The stale t0 entries should be swept, leaving just the t1 entry.
    assert await cache.size(now=t1) == 1
