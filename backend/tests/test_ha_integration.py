"""End-to-end: mutation via HTTP → lifespan bridge → FakeHAClient calls.

We monkey-patch `make_client_from_env` in `family_chores.app` before the
TestClient starts the lifespan, so the real app wires a `HABridge` around
our `FakeHAClient` and every mutation drives HA calls through it.

We also call `bridge.force_flush` directly after each mutation so we don't
have to sleep for the debounce window.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from family_chores import app as app_module
from family_chores.app import create_app
from family_chores.config import Options

from backend.tests._ha_fakes import FakeHAClient


@pytest.fixture
def fake_ha(monkeypatch):
    fake = FakeHAClient(time_zone="America/Chicago")
    monkeypatch.setattr(app_module, "make_client_from_env", lambda: fake)
    return fake


@pytest.fixture
def ha_client(tmp_path, monkeypatch, fake_ha):
    monkeypatch.setenv("FAMILY_CHORES_SKIP_SCHEDULER", "1")
    opts = Options(
        log_level="info",
        week_starts_on="monday",
        sound_default=False,
        timezone_override=None,  # exercise HA tz fetch path
        data_dir=tmp_path,
    )
    app = create_app(options=opts)
    with TestClient(app) as c:
        yield c


def _parent_auth(c) -> dict[str, str]:
    c.post("/api/auth/pin/set", json={"pin": "1234"})
    token = c.post("/api/auth/pin/verify", json={"pin": "1234"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


async def _force_flush(client: TestClient) -> None:
    bridge = client.app.state.bridge
    await bridge.force_flush()


def test_tz_is_resolved_from_ha_at_startup(ha_client, fake_ha):
    info = ha_client.get("/api/info").json()
    assert info["timezone"] == "America/Chicago"
    assert info["ha_connected"] is True
    assert any(m == "get_config" for m, _ in fake_ha.calls)


def test_creating_member_publishes_sensor(ha_client, fake_ha):
    headers = _parent_auth(ha_client)
    fake_ha.calls.clear()

    r = ha_client.post(
        "/api/members",
        json={
            "name": "Alice",
            "slug": "alice",
            "color": "#ff0000",
            "display_mode": "kid_standard",
            "requires_approval": False,
        },
        headers=headers,
    )
    assert r.status_code == 201

    asyncio.run(_force_flush(ha_client))

    set_states = [args for m, args in fake_ha.calls if m == "set_state"]
    entities = {args[0] for args in set_states}
    assert "sensor.family_chores_alice_points" in entities
    assert "sensor.family_chores_alice_streak" in entities


def test_completing_instance_syncs_todo_and_fires_event(ha_client, fake_ha):
    headers = _parent_auth(ha_client)

    ha_client.post(
        "/api/members",
        json={
            "name": "Alice",
            "slug": "alice",
            "color": "#ff0000",
            "display_mode": "kid_standard",
            "requires_approval": False,
            "ha_todo_entity_id": "todo.alice",
        },
        headers=headers,
    )
    ha_client.post(
        "/api/chores",
        json={
            "name": "Dishes",
            "points": 5,
            "active": True,
            "recurrence_type": "daily",
            "recurrence_config": {},
            "assigned_member_ids": [ha_client.get("/api/members/alice").json()["id"]],
        },
        headers=headers,
    )

    iid = ha_client.get("/api/today").json()["members"][0]["instances"][0]["id"]
    fake_ha.calls.clear()

    r = ha_client.post(f"/api/instances/{iid}/complete")
    assert r.status_code == 200

    asyncio.run(_force_flush(ha_client))

    # Todo item was created on the member's entity
    assert len(fake_ha.todo_lists["todo.alice"].items) == 1
    item = fake_ha.todo_lists["todo.alice"].items[0]
    assert item["summary"].startswith(f"[FC#{iid}] Dishes")
    # Its status was flipped to completed (follow-up update)
    assert item["status"] == "completed"

    # `family_chores_completed` event fired
    fired = [args for m, args in fake_ha.calls if m == "fire_event"]
    assert fired
    assert fired[0][0] == "family_chores_completed"
    payload = fired[0][1]
    assert payload["instance_id"] == iid
    assert payload["points"] == 5


def test_approve_fires_approved_event(ha_client, fake_ha):
    headers = _parent_auth(ha_client)

    # Member with approval required
    ha_client.post(
        "/api/members",
        json={
            "name": "Alice",
            "slug": "alice",
            "color": "#ff0000",
            "display_mode": "kid_standard",
            "requires_approval": True,
            "ha_todo_entity_id": "todo.alice",
        },
        headers=headers,
    )
    alice_id = ha_client.get("/api/members/alice").json()["id"]
    ha_client.post(
        "/api/chores",
        json={
            "name": "Dishes",
            "points": 5,
            "active": True,
            "recurrence_type": "daily",
            "recurrence_config": {},
            "assigned_member_ids": [alice_id],
        },
        headers=headers,
    )
    iid = ha_client.get("/api/today").json()["members"][0]["instances"][0]["id"]

    # Kid completes → done_unapproved → no completed event
    ha_client.post(f"/api/instances/{iid}/complete")
    asyncio.run(_force_flush(ha_client))
    pre_approve_events = [
        args for m, args in fake_ha.calls if m == "fire_event"
    ]
    assert all(
        args[0] != "family_chores_completed" for args in pre_approve_events
    )

    fake_ha.calls.clear()
    ha_client.post(f"/api/instances/{iid}/approve", headers=headers)
    asyncio.run(_force_flush(ha_client))

    fired = [args for m, args in fake_ha.calls if m == "fire_event"]
    assert fired and fired[0][0] == "family_chores_approved"


def test_events_queue_survives_unavailable_ha(ha_client, fake_ha):
    """A network blip should not lose events — they should retry."""
    from family_chores.ha.client import HAUnavailableError

    headers = _parent_auth(ha_client)
    ha_client.post(
        "/api/members",
        json={
            "name": "Alice",
            "slug": "alice",
            "color": "#f00",
            "display_mode": "kid_standard",
            "requires_approval": False,
        },
        headers=headers,
    )
    alice_id = ha_client.get("/api/members/alice").json()["id"]
    ha_client.post(
        "/api/chores",
        json={
            "name": "Dishes",
            "points": 5,
            "active": True,
            "recurrence_type": "daily",
            "recurrence_config": {},
            "assigned_member_ids": [alice_id],
        },
        headers=headers,
    )
    iid = ha_client.get("/api/today").json()["members"][0]["instances"][0]["id"]

    # First flush: fail the event fire
    fake_ha.fail_next["fire_event"] = HAUnavailableError("transient")
    ha_client.post(f"/api/instances/{iid}/complete")

    bridge = ha_client.app.state.bridge

    async def _first_flush_should_raise():
        with pytest.raises(HAUnavailableError):
            await bridge.force_flush()

    asyncio.run(_first_flush_should_raise())

    # The event should be back in the queue.
    assert len(bridge._event_backlog) == 1

    # Second flush: succeeds.
    asyncio.run(bridge.force_flush())
    fired = [args for m, args in fake_ha.calls if m == "fire_event"]
    assert any(args[0] == "family_chores_completed" for args in fired)
