"""Tests for the calendar-events extension on `/api/today` (DECISIONS §14 PR-B).

The today endpoint now embeds each member's calendar events for the
day. Two surfaces this enables: parent's home tile chip strip
(quick-glance prep items) and the kid view's "Today's events" section.

Stubbed provider lets us pin event payloads without HA. The provider
is replaced on `app.state` mid-test, mirroring the pattern in
`test_api_calendar.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from family_chores_api.services.calendar import (
    CalendarCache,
    CalendarProviderResult,
    RawEvent,
)


def _new_member_body(slug, calendar_entity_ids=None, **over):
    return {
        "name": over.get("name", slug.title()),
        "slug": slug,
        "color": over.get("color", "#ff0000"),
        "display_mode": over.get("display_mode", "kid_standard"),
        "requires_approval": over.get("requires_approval", False),
        "calendar_entity_ids": calendar_entity_ids or [],
    }


class _StubProvider:
    def __init__(self):
        self.calls: list[tuple[list[str], datetime, datetime]] = []
        self.next_response: CalendarProviderResult = CalendarProviderResult()

    async def get_events(self, entity_ids, from_dt, to_dt):
        self.calls.append((list(entity_ids), from_dt, to_dt))
        return self.next_response


@pytest.fixture
def provider_stub(client):
    stub = _StubProvider()
    client.app.state.calendar_provider = stub
    client.app.state.calendar_cache = CalendarCache()
    return stub


def _far_future_event(entity_id, summary, *, description=None):
    """An event in 2099 — guaranteed not to be filtered by hide_past
    no matter when the test runs."""
    start = datetime(2099, 6, 1, 16, 0, tzinfo=UTC)
    return RawEvent(
        entity_id=entity_id,
        summary=summary,
        description=description,
        start=start,
        end=start + timedelta(hours=1),
        all_day=False,
    )


def _far_past_event(entity_id, summary):
    """An event in 1999 — guaranteed to be filtered by hide_past."""
    start = datetime(1999, 6, 1, 16, 0, tzinfo=UTC)
    return RawEvent(
        entity_id=entity_id,
        summary=summary,
        description=None,
        start=start,
        end=start + timedelta(hours=1),
        all_day=False,
    )


# ─── shape ──────────────────────────────────────────────────────────────


def test_today_response_includes_calendar_events_field(client):
    """Even with no calendars mapped, the field exists as an empty
    list — the SPA can iterate without null-checking."""
    r = client.get("/api/today")
    assert r.status_code == 200
    body = r.json()
    # No members yet → empty members array, but the endpoint shape is fine.
    assert body["members"] == []


def test_today_member_has_empty_lists_when_no_calendars(client, parent_headers):
    client.post(
        "/api/members",
        json=_new_member_body("alice"),
        headers=parent_headers,
    )
    r = client.get("/api/today")
    assert r.status_code == 200
    body = r.json()
    assert len(body["members"]) == 1
    member = body["members"][0]
    assert member["calendar_events"] == []
    assert member["calendar_unreachable"] == []


# ─── happy-path enrichment ─────────────────────────────────────────────


def test_today_attaches_member_events(client, parent_headers, provider_stub):
    """A member with `calendar_entity_ids` set + a matching event
    from the provider → the event appears in `calendar_events` with
    the prep_items parsed."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice"]),
        headers=parent_headers,
    )
    provider_stub.next_response = CalendarProviderResult(
        events=[
            _far_future_event(
                "calendar.alice", "Soccer practice", description="Bring cleats"
            )
        ]
    )

    r = client.get("/api/today")
    assert r.status_code == 200, r.text
    member = r.json()["members"][0]
    assert len(member["calendar_events"]) == 1
    event = member["calendar_events"][0]
    assert event["summary"] == "Soccer practice"
    assert event["entity_id"] == "calendar.alice"
    assert event["prep_items"] == [{"label": "cleats", "icon": "🥾"}]


def test_today_hides_past_events(client, parent_headers, provider_stub):
    """Events whose `end` is in the past are filtered out (DECISIONS §14 Q7)."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice"]),
        headers=parent_headers,
    )
    provider_stub.next_response = CalendarProviderResult(
        events=[
            _far_past_event("calendar.alice", "Done already"),
            _far_future_event("calendar.alice", "Upcoming"),
        ]
    )

    r = client.get("/api/today")
    member = r.json()["members"][0]
    summaries = [e["summary"] for e in member["calendar_events"]]
    assert summaries == ["Upcoming"]


def test_shared_calendar_appears_under_each_member(
    client, parent_headers, provider_stub
):
    """Household-shared calendar events show up in every member's list
    (DECISIONS §14 Q9 — shared layer)."""
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
    provider_stub.next_response = CalendarProviderResult(
        events=[
            _far_future_event("calendar.alice", "Alice solo"),
            _far_future_event("calendar.bob", "Bob solo"),
            _far_future_event("calendar.family", "Family dinner"),
        ]
    )

    r = client.get("/api/today")
    members = {m["slug"]: m for m in r.json()["members"]}
    alice_summaries = {e["summary"] for e in members["alice"]["calendar_events"]}
    bob_summaries = {e["summary"] for e in members["bob"]["calendar_events"]}
    assert alice_summaries == {"Alice solo", "Family dinner"}
    assert bob_summaries == {"Bob solo", "Family dinner"}


def test_unreachable_propagates_to_only_affected_members(
    client, parent_headers, provider_stub
):
    """If `calendar.alice` fails but `calendar.bob` succeeds, only
    Alice's tile shows the unreachable hint."""
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
    provider_stub.next_response = CalendarProviderResult(
        events=[_far_future_event("calendar.bob", "Bob's event")],
        unreachable=["calendar.alice"],
    )

    r = client.get("/api/today")
    members = {m["slug"]: m for m in r.json()["members"]}
    assert members["alice"]["calendar_unreachable"] == ["calendar.alice"]
    assert members["alice"]["calendar_events"] == []
    assert members["bob"]["calendar_unreachable"] == []
    assert len(members["bob"]["calendar_events"]) == 1


def test_provider_not_called_when_no_entity_ids(client, parent_headers, provider_stub):
    """A member with no calendars mapped + no household shared → no
    provider call made for the household."""
    client.post(
        "/api/members",
        json=_new_member_body("alice"),
        headers=parent_headers,
    )
    r = client.get("/api/today")
    assert r.status_code == 200
    assert provider_stub.calls == []


# ─── degraded behaviour ─────────────────────────────────────────────────


def test_today_renders_chores_when_calendar_provider_raises(
    client, parent_headers, provider_stub
):
    """Calendar fetch is best-effort: if the provider blows up, the
    chore list still renders. The kid view must NEVER fail because
    of a calendar issue."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.alice"]),
        headers=parent_headers,
    )

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("provider exploded")

    provider_stub.get_events = _boom  # type: ignore[method-assign]

    r = client.get("/api/today")
    assert r.status_code == 200
    member = r.json()["members"][0]
    assert member["calendar_events"] == []
    assert member["calendar_unreachable"] == []


def test_calendar_dedupe_across_members(client, parent_headers, provider_stub):
    """A calendar listed under two members shouldn't be requested twice
    from the provider — verifies the dedupe in the entity-id roll-up."""
    client.post(
        "/api/members",
        json=_new_member_body("alice", calendar_entity_ids=["calendar.shared"]),
        headers=parent_headers,
    )
    client.post(
        "/api/members",
        json=_new_member_body("bob", calendar_entity_ids=["calendar.shared"]),
        headers=parent_headers,
    )
    provider_stub.next_response = CalendarProviderResult()
    r = client.get("/api/today")
    assert r.status_code == 200
    assert len(provider_stub.calls) == 1
    entity_ids, _, _ = provider_stub.calls[0]
    assert entity_ids == ["calendar.shared"]
