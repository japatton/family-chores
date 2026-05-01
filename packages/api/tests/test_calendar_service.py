"""Tests for the calendar composition service.

Covers `get_events_for_window` (the cache + provider + prep dance),
`partition_by_member` (the `/api/today` consumer shape), and `hide_past`
(the past-event filter callers use to keep the kid view clean).

A `_FakeProvider` records every call and returns canned `RawEvent`
batches so we can assert on call shape (entity_ids passed) and cache
behaviour (was the second call avoided?) without touching HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from family_chores_api.services.calendar.cache import CalendarCache
from family_chores_api.services.calendar.prep import PrepItem
from family_chores_api.services.calendar.provider import (
    CalendarProviderResult,
    RawEvent,
)
from family_chores_api.services.calendar.service import (
    CalendarEvent,
    get_events_for_window,
    hide_past,
    partition_by_member,
)


# ─── fakes ───────────────────────────────────────────────────────────────


@dataclass
class _FakeProvider:
    """Records every `get_events` call and replays a canned response.

    `responses` is a queue: each call pops the front. When empty, an
    empty result is returned (so tests don't have to over-specify
    when they only care about the first call)."""

    responses: list[CalendarProviderResult] = field(default_factory=list)
    calls: list[tuple[list[str], datetime, datetime]] = field(default_factory=list)

    async def get_events(
        self,
        entity_ids: list[str],
        from_dt: datetime,
        to_dt: datetime,
    ) -> CalendarProviderResult:
        self.calls.append((list(entity_ids), from_dt, to_dt))
        if self.responses:
            return self.responses.pop(0)
        return CalendarProviderResult()


def _ev(
    entity_id: str,
    summary: str,
    start: datetime,
    *,
    description: str | None = None,
    duration_minutes: int = 60,
) -> RawEvent:
    """Tiny event builder. Tz-aware so the produced events match the
    provider contract."""
    return RawEvent(
        entity_id=entity_id,
        summary=summary,
        description=description,
        start=start,
        end=start + timedelta(minutes=duration_minutes),
        all_day=False,
    )


# ─── get_events_for_window: empty / no-op paths ─────────────────────────


@pytest.mark.asyncio
async def test_empty_entity_ids_returns_empty_window():
    """No entities → no provider call, empty events list."""
    provider = _FakeProvider()
    cache = CalendarCache()
    window = await get_events_for_window(
        provider, cache, entity_ids=[],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 2, tzinfo=UTC),
    )
    assert window.events == []
    assert window.unreachable == []
    assert provider.calls == []


@pytest.mark.asyncio
async def test_inverted_window_returns_empty():
    """to_dt before from_dt → no days to query, no provider call."""
    provider = _FakeProvider()
    cache = CalendarCache()
    window = await get_events_for_window(
        provider, cache, entity_ids=["calendar.kid"],
        from_dt=datetime(2026, 5, 5, tzinfo=UTC),
        to_dt=datetime(2026, 5, 1, tzinfo=UTC),
    )
    assert window.events == []
    assert provider.calls == []


# ─── get_events_for_window: provider + cache integration ────────────────


@pytest.mark.asyncio
async def test_cache_miss_calls_provider_and_returns_events():
    """First call with cold cache: provider gets called, events flow
    through enriched into `CalendarEvent`."""
    soccer = _ev(
        "calendar.kid",
        "Soccer",
        datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
        description="Bring cleats",
    )
    provider = _FakeProvider(responses=[CalendarProviderResult(events=[soccer])])
    cache = CalendarCache()

    window = await get_events_for_window(
        provider, cache, entity_ids=["calendar.kid"],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 1, 23, 59, tzinfo=UTC),
    )

    assert len(provider.calls) == 1
    assert provider.calls[0][0] == ["calendar.kid"]
    assert len(window.events) == 1

    event = window.events[0]
    assert isinstance(event, CalendarEvent)
    assert event.summary == "Soccer"
    # Prep parsing kicks in: "Bring cleats" → cleats.
    assert event.prep_items == [PrepItem(label="cleats", icon="🥾")]


@pytest.mark.asyncio
async def test_second_call_uses_cache_no_provider():
    """After a fill, a second call for the same window doesn't re-hit
    the provider."""
    soccer = _ev("calendar.kid", "Soccer", datetime(2026, 5, 1, 16, 0, tzinfo=UTC))
    provider = _FakeProvider(responses=[CalendarProviderResult(events=[soccer])])
    cache = CalendarCache()
    window_args = dict(
        entity_ids=["calendar.kid"],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 1, 23, 59, tzinfo=UTC),
    )

    first = await get_events_for_window(provider, cache, **window_args)
    second = await get_events_for_window(provider, cache, **window_args)

    assert len(provider.calls) == 1  # only the cold call hit the provider
    assert len(first.events) == 1
    assert len(second.events) == 1
    assert second.events[0].summary == "Soccer"


@pytest.mark.asyncio
async def test_partial_cache_hit_still_calls_provider_for_missing_entity():
    """Cache has entity A's day cached; calling for [A, B] should still
    hit the provider — for B. (Whether A is also re-fetched or skipped
    is an implementation detail; what matters is B's data ends up in
    the result.)"""
    a_event = _ev("calendar.a", "A1", datetime(2026, 5, 1, 9, 0, tzinfo=UTC))
    b_event = _ev("calendar.b", "B1", datetime(2026, 5, 1, 10, 0, tzinfo=UTC))
    provider = _FakeProvider(responses=[CalendarProviderResult(events=[b_event])])
    cache = CalendarCache()

    # Pre-warm cache with A's day.
    from datetime import date
    await cache.put("calendar.a", date(2026, 5, 1), [a_event])

    window = await get_events_for_window(
        provider, cache, entity_ids=["calendar.a", "calendar.b"],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 1, 23, 59, tzinfo=UTC),
    )

    assert len(provider.calls) == 1
    # Provider should have been called for B (the missing entity).
    assert "calendar.b" in provider.calls[0][0]
    assert "calendar.a" not in provider.calls[0][0]

    summaries = sorted(e.summary for e in window.events)
    assert summaries == ["A1", "B1"]


@pytest.mark.asyncio
async def test_unreachable_entity_ids_propagate():
    """If the provider reports an entity as unreachable, the window
    surfaces it so the router can render a per-tile error state."""
    provider = _FakeProvider(
        responses=[
            CalendarProviderResult(events=[], unreachable=["calendar.broken"])
        ]
    )
    cache = CalendarCache()

    window = await get_events_for_window(
        provider, cache, entity_ids=["calendar.broken"],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 1, 23, 59, tzinfo=UTC),
    )

    assert window.events == []
    assert window.unreachable == ["calendar.broken"]


@pytest.mark.asyncio
async def test_unreachable_entity_is_not_cached():
    """An unreachable entity shouldn't poison the cache with an empty
    list — the next call must retry the provider."""
    provider = _FakeProvider(
        responses=[
            CalendarProviderResult(events=[], unreachable=["calendar.broken"]),
            # Second call: now reachable, returns an event.
            CalendarProviderResult(
                events=[
                    _ev(
                        "calendar.broken",
                        "Recovered",
                        datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
                    )
                ]
            ),
        ]
    )
    cache = CalendarCache()
    window_args = dict(
        entity_ids=["calendar.broken"],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 1, 23, 59, tzinfo=UTC),
    )

    first = await get_events_for_window(provider, cache, **window_args)
    assert first.events == []
    assert first.unreachable == ["calendar.broken"]

    # The retry should re-hit the provider, and now succeed.
    second = await get_events_for_window(provider, cache, **window_args)
    assert len(provider.calls) == 2
    assert len(second.events) == 1
    assert second.events[0].summary == "Recovered"


@pytest.mark.asyncio
async def test_events_sorted_by_start_then_entity_then_summary():
    """Result must have a stable order so the kid tile / monthly view
    don't reshuffle on every fetch."""
    e1 = _ev("calendar.b", "Z meeting", datetime(2026, 5, 1, 9, 0, tzinfo=UTC))
    e2 = _ev("calendar.a", "Earlier event", datetime(2026, 5, 1, 8, 0, tzinfo=UTC))
    e3 = _ev("calendar.a", "A meeting", datetime(2026, 5, 1, 9, 0, tzinfo=UTC))
    provider = _FakeProvider(responses=[CalendarProviderResult(events=[e1, e2, e3])])
    cache = CalendarCache()

    window = await get_events_for_window(
        provider, cache, entity_ids=["calendar.a", "calendar.b"],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 1, 23, 59, tzinfo=UTC),
    )

    summaries = [e.summary for e in window.events]
    # Earliest start first; then within same start, entity_id ascending,
    # then summary ascending.
    assert summaries == ["Earlier event", "A meeting", "Z meeting"]


@pytest.mark.asyncio
async def test_multi_day_window_caches_each_day_separately():
    """A 3-day fetch with one entity should populate 3 cache cells so
    subsequent single-day queries are hits."""
    e_day1 = _ev("calendar.kid", "D1", datetime(2026, 5, 1, 9, 0, tzinfo=UTC))
    e_day3 = _ev("calendar.kid", "D3", datetime(2026, 5, 3, 9, 0, tzinfo=UTC))
    provider = _FakeProvider(
        responses=[CalendarProviderResult(events=[e_day1, e_day3])]
    )
    cache = CalendarCache()

    # Initial 3-day fetch.
    await get_events_for_window(
        provider, cache, entity_ids=["calendar.kid"],
        from_dt=datetime(2026, 5, 1, tzinfo=UTC),
        to_dt=datetime(2026, 5, 3, 23, 59, tzinfo=UTC),
    )
    # Single-day follow-up should be served from cache.
    follow = await get_events_for_window(
        provider, cache, entity_ids=["calendar.kid"],
        from_dt=datetime(2026, 5, 2, tzinfo=UTC),
        to_dt=datetime(2026, 5, 2, 23, 59, tzinfo=UTC),
    )
    assert len(provider.calls) == 1  # day 2 served from cached empty.
    assert follow.events == []  # day 2 had no events.


# ─── partition_by_member ─────────────────────────────────────────────────


def _calendar_event(entity_id: str, summary: str) -> CalendarEvent:
    return CalendarEvent(
        entity_id=entity_id,
        summary=summary,
        description=None,
        start=datetime(2026, 5, 1, 9, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        all_day=False,
        location=None,
        prep_items=[],
    )


def test_partition_by_member_groups_by_entity_id():
    events = [
        _calendar_event("calendar.alice", "Alice's lesson"),
        _calendar_event("calendar.bob", "Bob's practice"),
        _calendar_event("calendar.alice", "Alice's recital"),
    ]
    grouped = partition_by_member(
        events, {1: ["calendar.alice"], 2: ["calendar.bob"]}
    )
    assert [e.summary for e in grouped[1]] == ["Alice's lesson", "Alice's recital"]
    assert [e.summary for e in grouped[2]] == ["Bob's practice"]


def test_partition_by_member_keeps_empty_member_buckets():
    """A member with no events still appears as `{member_id: []}` so
    UI consumers don't need to handle KeyError."""
    grouped = partition_by_member([], {1: ["calendar.a"], 2: ["calendar.b"]})
    assert grouped == {1: [], 2: []}


def test_partition_by_member_assigns_shared_event_to_each_owner():
    """If two members both list the household calendar, the event
    appears under both — the caller decides whether to dedupe."""
    shared = _calendar_event("calendar.shared", "Family dinner")
    grouped = partition_by_member(
        [shared],
        {
            1: ["calendar.alice", "calendar.shared"],
            2: ["calendar.bob", "calendar.shared"],
        },
    )
    assert [e.summary for e in grouped[1]] == ["Family dinner"]
    assert [e.summary for e in grouped[2]] == ["Family dinner"]


def test_partition_by_member_drops_orphan_events():
    """An event whose entity isn't in any member's list is silently
    dropped — could be a stale entity or a calendar removed from
    every member's list."""
    orphan = _calendar_event("calendar.unmapped", "Mystery meeting")
    grouped = partition_by_member([orphan], {1: ["calendar.alice"]})
    assert grouped == {1: []}


# ─── hide_past ───────────────────────────────────────────────────────────


def test_hide_past_drops_events_ending_before_now():
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    past = CalendarEvent(
        entity_id="c1",
        summary="Done",
        description=None,
        start=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
        all_day=False,
        location=None,
        prep_items=[],
    )
    future = CalendarEvent(
        entity_id="c1",
        summary="Coming up",
        description=None,
        start=datetime(2026, 5, 1, 13, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
        all_day=False,
        location=None,
        prep_items=[],
    )
    out = hide_past([past, future], now=now)
    assert [e.summary for e in out] == ["Coming up"]


def test_hide_past_keeps_event_ending_exactly_at_now():
    """`end == now` is treated as still-current (DECISIONS §14 Q7 says
    'hide once event.end < now', so equal stays)."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    boundary = CalendarEvent(
        entity_id="c1",
        summary="Just ending",
        description=None,
        start=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
        end=now,
        all_day=False,
        location=None,
        prep_items=[],
    )
    out = hide_past([boundary], now=now)
    assert out == [boundary]


def test_hide_past_handles_naive_now_as_utc():
    """A naive `now` is treated as UTC so callers don't need to thread
    tzinfo through every layer."""
    now_naive = datetime(2026, 5, 1, 12, 0)  # no tzinfo
    past = CalendarEvent(
        entity_id="c1",
        summary="Done",
        description=None,
        start=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
        all_day=False,
        location=None,
        prep_items=[],
    )
    future = CalendarEvent(
        entity_id="c1",
        summary="Future",
        description=None,
        start=datetime(2026, 5, 1, 13, 0, tzinfo=UTC),
        end=datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
        all_day=False,
        location=None,
        prep_items=[],
    )
    out = hide_past([past, future], now=now_naive)
    assert [e.summary for e in out] == ["Future"]


def test_hide_past_handles_naive_event_end_as_utc():
    """A malformed feed with naive event ends shouldn't crash the
    filter; we treat them as UTC and apply the same rule."""
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    naive_past = CalendarEvent(
        entity_id="c1",
        summary="NaivePast",
        description=None,
        start=datetime(2026, 5, 1, 10, 0),
        end=datetime(2026, 5, 1, 11, 0),  # naive
        all_day=False,
        location=None,
        prep_items=[],
    )
    out = hide_past([naive_past], now=now)
    assert out == []


def test_hide_past_default_now_uses_wall_clock():
    """No `now` arg → uses `datetime.now(UTC)`. We can't pin the wall
    clock, but we can assert the function doesn't crash and that an
    obviously-far-future event survives."""
    far_future = CalendarEvent(
        entity_id="c1",
        summary="2099",
        description=None,
        start=datetime(2099, 1, 1, tzinfo=UTC),
        end=datetime(2099, 1, 2, tzinfo=UTC),
        all_day=False,
        location=None,
        prep_items=[],
    )
    out = hide_past([far_future])
    assert out == [far_future]


def test_hide_past_empty_input_returns_empty():
    out = hide_past([], now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC))
    assert out == []
