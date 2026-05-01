"""Tests for `HACalendarProvider` — HA `calendar.get_events` parsing,
per-entity unreachability, and transport-error fallback.

The provider is the addon's adapter between HA's REST shape and the
provider-agnostic `CalendarProviderResult` the service layer consumes.
We exercise it against the in-memory `FakeHAClient`; full end-to-end
parsing of real HA payloads is covered by `test_ha_integration.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from family_chores_addon.ha.calendar import HACalendarProvider
from family_chores_addon.ha.client import (
    HAClient,
    HAServerError,
    HAUnauthorizedError,
    HAUnavailableError,
)

from ._ha_fakes import FakeHAClient


def _make_provider(
    canned: dict[str, Any] | None,
    *,
    fail: Exception | None = None,
) -> tuple[HACalendarProvider, FakeHAClient]:
    """Build a provider with one canned `service_response` payload.

    `canned` is the inner `service_response` dict; the wrapper
    constructs the full `{"service_response": canned}` envelope. Pass
    `fail` to inject an exception on the next `call_service`.
    """
    fake = FakeHAClient()
    if canned is not None:
        fake.service_responses[("calendar", "get_events")] = [
            {"service_response": canned}
        ]
    if fail is not None:
        fake.fail_next["call_service"] = fail
    provider = HACalendarProvider(cast(HAClient, fake))
    return provider, fake


_FROM = datetime(2026, 5, 1, 0, 0, tzinfo=UTC)
_TO = datetime(2026, 5, 1, 23, 59, tzinfo=UTC)


# ─── empty / no-op ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_entity_ids_returns_empty_no_call():
    provider, fake = _make_provider(canned={})
    result = await provider.get_events([], _FROM, _TO)
    assert result.events == []
    assert result.unreachable == []
    # No service call should have been issued.
    assert fake.calls == []


# ─── happy-path parsing ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parses_timed_event():
    provider, _ = _make_provider(
        canned={
            "calendar.kid": {
                "events": [
                    {
                        "start": "2026-05-01T16:00:00-07:00",
                        "end": "2026-05-01T17:30:00-07:00",
                        "summary": "Soccer practice",
                        "description": "Bring cleats and water",
                        "location": "School field",
                    }
                ]
            }
        }
    )
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert result.unreachable == []
    assert len(result.events) == 1

    event = result.events[0]
    assert event.entity_id == "calendar.kid"
    assert event.summary == "Soccer practice"
    assert event.description == "Bring cleats and water"
    assert event.location == "School field"
    assert event.all_day is False
    # Timezone preserved from the upstream (-07:00).
    assert event.start.tzinfo is not None
    assert event.start.utcoffset() is not None


@pytest.mark.asyncio
async def test_parses_all_day_event():
    """Date-only start/end → `all_day=True`, midnight UTC datetimes."""
    provider, _ = _make_provider(
        canned={
            "calendar.kid": {
                "events": [
                    {
                        "start": "2026-05-01",
                        "end": "2026-05-08",
                        "summary": "Spring Break",
                        "description": None,
                        "location": None,
                    }
                ]
            }
        }
    )
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert len(result.events) == 1
    event = result.events[0]
    assert event.all_day is True
    assert event.start == datetime(2026, 5, 1, tzinfo=UTC)
    assert event.end == datetime(2026, 5, 8, tzinfo=UTC)
    assert event.description is None
    assert event.location is None


@pytest.mark.asyncio
async def test_naive_datetime_treated_as_utc():
    """An ISO datetime without offset gets UTC tagged so downstream
    comparisons (hide_past, sort) don't blow up."""
    provider, _ = _make_provider(
        canned={
            "calendar.kid": {
                "events": [
                    {
                        "start": "2026-05-01T16:00:00",
                        "end": "2026-05-01T17:00:00",
                        "summary": "Naive event",
                    }
                ]
            }
        }
    )
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert len(result.events) == 1
    assert result.events[0].start.tzinfo is UTC


@pytest.mark.asyncio
async def test_call_payload_uses_iso_window_and_entity_list():
    """The provider must pass the entity list and ISO-formatted window
    bounds to HA — verify the actual request shape."""
    provider, fake = _make_provider(canned={"calendar.kid": {"events": []}})
    await provider.get_events(["calendar.kid", "calendar.shared"], _FROM, _TO)

    # Find the calendar.get_events call.
    matching = [
        c for c in fake.calls
        if c[0] == "call_service" and c[1][0] == "calendar" and c[1][1] == "get_events"
    ]
    assert len(matching) == 1
    _, (_, _, data, return_response) = matching[0]
    assert data["entity_id"] == ["calendar.kid", "calendar.shared"]
    assert data["start_date_time"] == "2026-05-01T00:00:00+00:00"
    assert data["end_date_time"] == "2026-05-01T23:59:00+00:00"
    assert return_response is True


@pytest.mark.asyncio
async def test_naive_window_bounds_get_utc_tag():
    """Defensive: callers that pass naive `from_dt`/`to_dt` shouldn't
    silently shift the window."""
    provider, fake = _make_provider(canned={"calendar.kid": {"events": []}})
    await provider.get_events(
        ["calendar.kid"],
        datetime(2026, 5, 1),  # naive
        datetime(2026, 5, 1, 23, 59),  # naive
    )
    call = next(c for c in fake.calls if c[0] == "call_service")
    _, (_, _, data, _) = call
    assert data["start_date_time"].endswith("+00:00")
    assert data["end_date_time"].endswith("+00:00")


# ─── multi-entity + per-entity unreachable ──────────────────────────────


@pytest.mark.asyncio
async def test_multiple_entities_in_one_call():
    """One service call covers all entities; events come back tagged
    with their entity_id."""
    provider, _ = _make_provider(
        canned={
            "calendar.kid_a": {
                "events": [
                    {
                        "start": "2026-05-01T09:00:00+00:00",
                        "end": "2026-05-01T10:00:00+00:00",
                        "summary": "A's lesson",
                    }
                ]
            },
            "calendar.kid_b": {
                "events": [
                    {
                        "start": "2026-05-01T10:00:00+00:00",
                        "end": "2026-05-01T11:00:00+00:00",
                        "summary": "B's practice",
                    }
                ]
            },
        }
    )
    result = await provider.get_events(["calendar.kid_a", "calendar.kid_b"], _FROM, _TO)
    assert result.unreachable == []
    by_entity = {e.entity_id: e for e in result.events}
    assert by_entity["calendar.kid_a"].summary == "A's lesson"
    assert by_entity["calendar.kid_b"].summary == "B's practice"


@pytest.mark.asyncio
async def test_missing_entity_in_response_is_unreachable():
    """If HA omits an entity from the response block, treat it as
    unreachable (NOT 'no events') so the parent gets a real signal."""
    provider, _ = _make_provider(
        canned={
            "calendar.kid_a": {"events": []},
            # calendar.kid_b is missing entirely.
        }
    )
    result = await provider.get_events(["calendar.kid_a", "calendar.kid_b"], _FROM, _TO)
    assert result.events == []
    assert result.unreachable == ["calendar.kid_b"]


@pytest.mark.asyncio
async def test_entity_with_empty_events_list_is_not_unreachable():
    """An empty events list is a valid 'no events that day' signal,
    distinct from 'couldn't reach'."""
    provider, _ = _make_provider(canned={"calendar.kid": {"events": []}})
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert result.events == []
    assert result.unreachable == []


@pytest.mark.asyncio
async def test_entity_block_wrong_shape_is_unreachable():
    """If HA returns something weird (not a dict), don't crash; mark
    that entity as unreachable."""
    provider, _ = _make_provider(
        canned={"calendar.kid": "not a dict"}  # type: ignore[dict-item]
    )
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert result.events == []
    assert result.unreachable == ["calendar.kid"]


@pytest.mark.asyncio
async def test_events_field_wrong_shape_is_unreachable():
    """events: <not a list> → unreachable."""
    provider, _ = _make_provider(
        canned={"calendar.kid": {"events": "not a list"}}
    )
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert result.events == []
    assert result.unreachable == ["calendar.kid"]


# ─── transport error fallback ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_unavailable_marks_all_entities_unreachable():
    provider, _ = _make_provider(
        canned=None, fail=HAUnavailableError("connection refused")
    )
    result = await provider.get_events(
        ["calendar.kid", "calendar.shared"], _FROM, _TO
    )
    assert result.events == []
    assert sorted(result.unreachable) == ["calendar.kid", "calendar.shared"]


@pytest.mark.asyncio
async def test_unauthorized_marks_all_entities_unreachable():
    provider, _ = _make_provider(canned=None, fail=HAUnauthorizedError("401"))
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert result.events == []
    assert result.unreachable == ["calendar.kid"]


@pytest.mark.asyncio
async def test_server_error_marks_all_entities_unreachable():
    provider, _ = _make_provider(canned=None, fail=HAServerError("502"))
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert result.events == []
    assert result.unreachable == ["calendar.kid"]


# ─── malformed response shape ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_without_service_response_block_is_unreachable():
    provider, fake = _make_provider(canned={})
    # Stomp the canned response with a shape missing service_response.
    fake.service_responses[("calendar", "get_events")] = [{"unexpected": "shape"}]
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    # No service_response → block is empty dict → entity missing → unreachable.
    assert result.events == []
    assert result.unreachable == ["calendar.kid"]


@pytest.mark.asyncio
async def test_response_with_garbage_service_response_is_all_unreachable():
    """If service_response is the wrong type, treat everything as
    unreachable rather than crashing."""
    provider, fake = _make_provider(canned={})
    fake.service_responses[("calendar", "get_events")] = [
        {"service_response": "garbage"}
    ]
    result = await provider.get_events(
        ["calendar.kid", "calendar.shared"], _FROM, _TO
    )
    assert result.events == []
    assert sorted(result.unreachable) == ["calendar.kid", "calendar.shared"]


@pytest.mark.asyncio
async def test_none_response_is_all_unreachable():
    """HA returning None (no service_response at all) → every requested
    entity is unreachable."""
    provider, fake = _make_provider(canned={})
    fake.service_responses[("calendar", "get_events")] = [None]
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    # `_parse_response(None, [...])` → service_block = {} → entity missing.
    assert result.events == []
    assert result.unreachable == ["calendar.kid"]


# ─── garbage events get dropped, good ones survive ──────────────────────


@pytest.mark.asyncio
async def test_garbage_events_dropped_good_ones_kept():
    """One bad event in a list shouldn't drop the whole calendar."""
    provider, _ = _make_provider(
        canned={
            "calendar.kid": {
                "events": [
                    "not a dict",  # garbage
                    {"summary": "", "start": "2026-05-01T09:00:00+00:00", "end": "2026-05-01T10:00:00+00:00"},  # empty summary
                    {"summary": "No start"},  # missing start/end
                    {  # the only good one
                        "summary": "Good event",
                        "start": "2026-05-01T09:00:00+00:00",
                        "end": "2026-05-01T10:00:00+00:00",
                    },
                    {  # malformed datetime
                        "summary": "Bad date",
                        "start": "not a date",
                        "end": "2026-05-01T10:00:00+00:00",
                    },
                ]
            }
        }
    )
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    # Calendar reachable (response present), garbage filtered.
    assert result.unreachable == []
    assert len(result.events) == 1
    assert result.events[0].summary == "Good event"


@pytest.mark.asyncio
async def test_non_string_description_dropped_to_none():
    provider, _ = _make_provider(
        canned={
            "calendar.kid": {
                "events": [
                    {
                        "summary": "Event",
                        "start": "2026-05-01T09:00:00+00:00",
                        "end": "2026-05-01T10:00:00+00:00",
                        "description": 42,  # wrong type
                        "location": ["weird"],  # wrong type
                    }
                ]
            }
        }
    )
    result = await provider.get_events(["calendar.kid"], _FROM, _TO)
    assert len(result.events) == 1
    assert result.events[0].description is None
    assert result.events[0].location is None
