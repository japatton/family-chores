"""HTTP tests for chore CRUD + recurrence-config validation."""

from __future__ import annotations


def _member(client, parent_headers, slug="alice") -> int:
    r = client.post(
        "/api/members",
        json={
            "name": slug.title(),
            "slug": slug,
            "color": "#ff0000",
            "display_mode": "kid_standard",
            "requires_approval": False,
        },
        headers=parent_headers,
    )
    assert r.status_code == 201
    return r.json()["id"]


def _chore_body(name="Dishes", members=None, **over):
    body = {
        "name": name,
        "points": 5,
        "active": True,
        "recurrence_type": "daily",
        "recurrence_config": {},
        "assigned_member_ids": members or [],
    }
    body.update(over)
    return body


def test_list_chores_empty(client):
    assert client.get("/api/chores").json() == []


def test_create_chore_requires_parent(client):
    r = client.post("/api/chores", json=_chore_body())
    assert r.status_code == 401


def test_create_chore_happy_path(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Dishes"
    assert body["assigned_member_ids"] == [alice_id]


def test_create_chore_unknown_member_404(client, parent_headers):
    r = client.post(
        "/api/chores", json=_chore_body(members=[999]), headers=parent_headers
    )
    assert r.status_code == 404


def test_create_chore_with_valid_specific_days_config(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="specific_days",
            recurrence_config={"days": [1, 3, 5]},
        ),
        headers=parent_headers,
    )
    assert r.status_code == 201
    assert r.json()["recurrence_config"] == {"days": [1, 3, 5]}


def test_create_chore_with_invalid_specific_days_422(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="specific_days",
            recurrence_config={"days": [0, 9]},  # invalid ISO weekdays
        ),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_create_chore_monthly_31_accepted(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="monthly_on_date", recurrence_config={"day": 31}
        ),
        headers=parent_headers,
    )
    assert r.status_code == 201


def test_create_chore_monthly_invalid_day_422(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="monthly_on_date", recurrence_config={"day": 32}
        ),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_create_chore_once_requires_date(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(recurrence_type="once", recurrence_config={}),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_every_n_days_requires_anchor(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="every_n_days", recurrence_config={"n": 3}
        ),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_patch_chore(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    chore_id = r.json()["id"]
    r = client.patch(
        f"/api/chores/{chore_id}",
        json={"points": 20, "active": False},
        headers=parent_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["points"] == 20
    assert body["active"] is False


def test_patch_chore_changes_assignments(client, parent_headers):
    alice_id = _member(client, parent_headers, "alice")
    bob_id = _member(client, parent_headers, "bob")
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    chore_id = r.json()["id"]
    r = client.patch(
        f"/api/chores/{chore_id}",
        json={"assigned_member_ids": [bob_id]},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["assigned_member_ids"] == [bob_id]


def test_delete_chore_cascades_instances(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    chore_id = r.json()["id"]

    # Today's instance should exist (create_chore triggers generate_instances)
    today = client.get("/api/today").json()
    assert len(today["members"][0]["instances"]) == 1

    assert client.delete(f"/api/chores/{chore_id}", headers=parent_headers).status_code == 204

    today = client.get("/api/today").json()
    assert today["members"][0]["instances"] == []


def test_list_chores_filter_by_member(client, parent_headers):
    alice_id = _member(client, parent_headers, "alice")
    bob_id = _member(client, parent_headers, "bob")
    client.post(
        "/api/chores",
        json=_chore_body("Dishes", members=[alice_id]),
        headers=parent_headers,
    )
    client.post(
        "/api/chores",
        json=_chore_body("Laundry", members=[bob_id]),
        headers=parent_headers,
    )

    r = client.get("/api/chores", params={"member_id": alice_id})
    assert {c["name"] for c in r.json()} == {"Dishes"}


def test_list_chores_filter_by_active(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores",
        json=_chore_body(members=[alice_id], active=False),
        headers=parent_headers,
    )
    assert r.status_code == 201

    active_only = client.get("/api/chores", params={"active": True}).json()
    assert active_only == []
    inactive_only = client.get("/api/chores", params={"active": False}).json()
    assert len(inactive_only) == 1
