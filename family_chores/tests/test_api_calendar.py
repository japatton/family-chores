"""HTTP tests for `/api/calendar` (DECISIONS §14).

The fixture-injected app uses `NoOpCalendarProvider` because no HA
client is configured in tests, so most assertions are about the
endpoint shape, validation, and entity_id resolution. End-to-end
provider behaviour is covered by the addon-side
`test_ha_calendar_provider.py` and the service-layer tests in
`packages/api/tests/test_calendar_service.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from family_chores_api.services.calendar import (
    CalendarProviderResult,
    RawEvent,
)


def _new_member_body(slug="alice", calendar_entity_ids=None, **over):
    return {
        "name": over.get("name", slug.title()),
        "slug": slug,
        "color": over.get("color", "#ff0000"),
        "display_mode": over.get("display_mode", "kid_standard"),
        "requires_approval": over.get("requires_approval", False),
        "calendar_entity_ids": calendar_entity_ids or [],
    }


# ─── shape + validation ──────────────────────────────────────────────────


def test_get_events_requires_from_and_to(client):
    """Missing query params → 422 from FastAPI's request validation."""
    r = client.get("/api/calendar/events")
    assert r.status_code == 422


def test_get_events_rejects_inverted_window(client):
    """to < from → 400 with the domain validation_error code."""
    r = client.get(
        "/api/calendar/events",
        params={"from": "2026-05-05T00:00:00Z", "to": "2026-05-01T00:00:00Z"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "validation_error"


def test_get_events_returns_empty_when_no_calendars_mapped(client):
    """No calendar mapping anywhere → empty events, no provider call,
    no error."""
    r = client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []
    assert body["unreachable"] == []


def test_get_events_unknown_member_id_returns_404(client, parent_headers):
    r = client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": 99999,
        },
    )
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


# ─── refresh ────────────────────────────────────────────────────────────


def test_refresh_requires_parent(client):
    r = client.post("/api/calendar/refresh")
    assert r.status_code == 401
    assert r.json()["error"] == "auth_required"


def test_refresh_returns_count(client, parent_headers):
    """Empty cache → 0 dropped, 200."""
    r = client.post("/api/calendar/refresh", headers=parent_headers)
    assert r.status_code == 200
    assert r.json() == {"invalidated": 0}


# ─── entity_id resolution + provider integration ────────────────────────


class _StubProvider:
    """Records calls and returns a canned response. Plugged in by the
    `provider_stub` fixture so we can drive the resolution logic
    without HA."""

    def __init__(self):
        self.calls: list[tuple[list[str], datetime, datetime]] = []
        self.next_response: CalendarProviderResult = CalendarProviderResult()

    async def get_events(self, entity_ids, from_dt, to_dt):
        self.calls.append((list(entity_ids), from_dt, to_dt))
        return self.next_response


@pytest.fixture
def provider_stub(client):
    """Replace the lifespan-installed NoOpCalendarProvider with a
    recording stub. Returns the stub for assertions."""
    stub = _StubProvider()
    client.app.state.calendar_provider = stub
    # Cache is also stomped fresh so prior tests don't leak.
    from family_chores_api.services.calendar import CalendarCache
    client.app.state.calendar_cache = CalendarCache()
    return stub


def test_get_events_calls_provider_with_member_calendars(
    client, parent_headers, provider_stub
):
    """member_id set → provider gets that member's calendar ids
    (plus any household-shared ones — empty here)."""
    client.post(
        "/api/members",
        json=_new_member_body(
            "alice", calendar_entity_ids=["calendar.alice", "calendar.alice_school"]
        ),
        headers=parent_headers,
    )
    member_id = client.get("/api/members/alice").json()["id"]

    provider_stub.next_response = CalendarProviderResult(
        events=[
            RawEvent(
                entity_id="calendar.alice",
                summary="Soccer",
                description="Bring cleats",
                start=datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
                end=datetime(2026, 5, 1, 17, 30, tzinfo=UTC),
                all_day=False,
            )
        ]
    )

    r = client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["events"]) == 1
    event = body["events"][0]
    assert event["summary"] == "Soccer"
    # Prep parsing kicked in.
    assert event["prep_items"] == [{"label": "cleats", "icon": "🥾"}]

    # Provider was called with the member's two calendars.
    assert len(provider_stub.calls) == 1
    entity_ids, _, _ = provider_stub.calls[0]
    assert sorted(entity_ids) == ["calendar.alice", "calendar.alice_school"]


def test_get_events_includes_household_shared_for_member(
    client, parent_headers, provider_stub
):
    """member_id set + household has shared_calendar_entity_ids → both
    sets are union-de-duped."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice"]),
        headers=parent_headers,
    )
    member_id = client.get("/api/members/alice").json()["id"]
    client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": ["calendar.family", "calendar.alice"]},
        headers=parent_headers,
    )
    # PUT triggered cache invalidation; reset the stub's call log to
    # ignore any pre-existing state that bled through.
    provider_stub.calls.clear()

    r = client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert r.status_code == 200

    entity_ids, _, _ = provider_stub.calls[0]
    # `calendar.alice` appears once (de-duped); both shared and
    # per-member contribute.
    assert sorted(entity_ids) == ["calendar.alice", "calendar.family"]


def test_get_events_no_member_id_uses_all_member_calendars_plus_shared(
    client, parent_headers, provider_stub
):
    """Parent's monthly view: no member_id → every member's calendars
    plus the household-shared list."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice"]),
        headers=parent_headers,
    )
    client.post(
        "/api/members",
        json=_new_member_body("bob", calendar_entity_ids=["calendar.bob"]),
        headers=parent_headers,
    )
    client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": ["calendar.family"]},
        headers=parent_headers,
    )
    provider_stub.calls.clear()

    r = client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
        },
    )
    assert r.status_code == 200

    entity_ids, _, _ = provider_stub.calls[0]
    assert sorted(entity_ids) == ["calendar.alice", "calendar.bob", "calendar.family"]


def test_get_events_propagates_unreachable(client, parent_headers, provider_stub):
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.broken"]),
        headers=parent_headers,
    )
    member_id = client.get("/api/members/alice").json()["id"]
    provider_stub.next_response = CalendarProviderResult(
        events=[], unreachable=["calendar.broken"]
    )

    r = client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["events"] == []
    assert body["unreachable"] == ["calendar.broken"]


# ─── cache invalidation hooks ───────────────────────────────────────────


def test_household_settings_change_invalidates_cache(
    client, parent_headers, provider_stub
):
    """A PUT that changes shared_calendar_entity_ids should drop the
    cache so the next read re-hits the provider — the cache is
    populated by the first call, and the second call after PUT
    proves no stale data leaks."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice"]),
        headers=parent_headers,
    )
    member_id = client.get("/api/members/alice").json()["id"]
    provider_stub.next_response = CalendarProviderResult(
        events=[
            RawEvent(
                entity_id="calendar.alice",
                summary="A",
                description=None,
                start=datetime(2026, 5, 1, 16, 0, tzinfo=UTC),
                end=datetime(2026, 5, 1, 17, 0, tzinfo=UTC),
                all_day=False,
            )
        ]
    )
    # First call populates the cache.
    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 1
    # Second call would use cache (no change to entity list).
    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 1  # served from cache

    # Now change shared settings — should drop the cache.
    client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": ["calendar.family"]},
        headers=parent_headers,
    )
    # Third call: new entity set + cache busted → provider hit.
    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 2


def test_member_calendar_change_invalidates_cache(
    client, parent_headers, provider_stub
):
    """PATCHing a member's calendar_entity_ids should drop the cache
    so the next read picks up the new entity list immediately."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice_v1"]),
        headers=parent_headers,
    )
    member_id = client.get("/api/members/alice").json()["id"]
    provider_stub.next_response = CalendarProviderResult()
    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 1

    # Cache hit on second call (entity list unchanged).
    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 1

    # Change member calendars — cache busted.
    client.patch(
        "/api/members/alice",
        json={"calendar_entity_ids": ["calendar.alice_v2"]},
        headers=parent_headers,
    )
    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 2


def test_refresh_endpoint_invalidates_cache(client, parent_headers, provider_stub):
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice"]),
        headers=parent_headers,
    )
    member_id = client.get("/api/members/alice").json()["id"]
    provider_stub.next_response = CalendarProviderResult()
    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 1

    r = client.post("/api/calendar/refresh", headers=parent_headers)
    assert r.status_code == 200
    # The single cell from the previous call should have been dropped.
    assert r.json()["invalidated"] >= 1

    client.get(
        "/api/calendar/events",
        params={
            "from": "2026-05-01T00:00:00Z",
            "to": "2026-05-01T23:59:59Z",
            "member_id": member_id,
        },
    )
    assert len(provider_stub.calls) == 2


def test_member_create_with_calendar_entity_ids_persisted(client, parent_headers):
    """The new MemberRead should expose calendar_entity_ids as set on
    create."""
    r = client.post(
        "/api/members",
        json=_new_member_body(
            "alice", calendar_entity_ids=["calendar.alice", "calendar.alice_school"]
        ),
        headers=parent_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["calendar_entity_ids"] == [
        "calendar.alice",
        "calendar.alice_school",
    ]

    # And on subsequent GETs.
    r2 = client.get("/api/members/alice")
    assert r2.json()["calendar_entity_ids"] == [
        "calendar.alice",
        "calendar.alice_school",
    ]


def test_member_create_with_invalid_entity_id_rejected(client, parent_headers):
    r = client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["sensor.kitchen"]),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_default_window_uses_today(client):
    """Sanity: window can span days fine — the API doesn't impose a
    max range, the provider does its own thing."""
    today = datetime.now(UTC).date()
    a_week_out = today + timedelta(days=7)
    r = client.get(
        "/api/calendar/events",
        params={
            "from": f"{today.isoformat()}T00:00:00Z",
            "to": f"{a_week_out.isoformat()}T23:59:59Z",
        },
    )
    assert r.status_code == 200
