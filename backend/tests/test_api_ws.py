"""WebSocket behaviour — hello on connect, ping/pong, mutation broadcasts."""

from __future__ import annotations


def test_ws_sends_hello_on_connect(client):
    with client.websocket_connect("/api/ws") as ws:
        hello = ws.receive_json()
        assert hello == {"type": "hello"}


def test_ws_ping_pong(client):
    with client.websocket_connect("/api/ws") as ws:
        ws.receive_json()  # hello
        ws.send_text("ping")
        assert ws.receive_text() == "pong"


def test_ws_broadcasts_member_created(client, parent_headers):
    with client.websocket_connect("/api/ws") as ws:
        ws.receive_json()  # hello
        r = client.post(
            "/api/members",
            json={
                "name": "Alice",
                "slug": "alice",
                "color": "#ff0000",
                "display_mode": "kid_standard",
                "requires_approval": False,
            },
            headers=parent_headers,
        )
        assert r.status_code == 201
        alice_id = r.json()["id"]
        event = ws.receive_json()
        assert event["type"] == "member_created"
        assert event["member_id"] == alice_id


def test_ws_broadcasts_instance_updated_on_complete(client, parent_headers):
    # Set up a member + chore first (before connecting, to reduce noise).
    client.post(
        "/api/members",
        json={
            "name": "Alice",
            "slug": "alice",
            "color": "#ff0000",
            "display_mode": "kid_standard",
            "requires_approval": False,
        },
        headers=parent_headers,
    )
    alice = client.get("/api/members/alice").json()
    client.post(
        "/api/chores",
        json={
            "name": "Dishes",
            "points": 5,
            "active": True,
            "recurrence_type": "daily",
            "recurrence_config": {},
            "assigned_member_ids": [alice["id"]],
        },
        headers=parent_headers,
    )
    iid = client.get("/api/today").json()["members"][0]["instances"][0]["id"]

    with client.websocket_connect("/api/ws") as ws:
        ws.receive_json()  # hello
        client.post(f"/api/instances/{iid}/complete")
        event = ws.receive_json()
        assert event["type"] == "instance_updated"
        assert event["instance_id"] == iid
        assert event["state"] == "done"
