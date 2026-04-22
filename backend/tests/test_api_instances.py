"""HTTP tests for instance state transitions and the `/api/today` view."""

from __future__ import annotations


def _seed(client, parent_headers, *, requires_approval=False, points=5) -> tuple[int, int, int]:
    """Create alice + a daily chore assigned to alice; return (member_id, chore_id, instance_id)."""
    r = client.post(
        "/api/members",
        json={
            "name": "Alice",
            "slug": "alice",
            "color": "#ff0000",
            "display_mode": "kid_standard",
            "requires_approval": requires_approval,
        },
        headers=parent_headers,
    )
    alice_id = r.json()["id"]

    r = client.post(
        "/api/chores",
        json={
            "name": "Dishes",
            "points": points,
            "active": True,
            "recurrence_type": "daily",
            "recurrence_config": {},
            "assigned_member_ids": [alice_id],
        },
        headers=parent_headers,
    )
    chore_id = r.json()["id"]

    today = client.get("/api/today").json()
    instance_id = today["members"][0]["instances"][0]["id"]
    return alice_id, chore_id, instance_id


# ─── today view ───────────────────────────────────────────────────────────


def test_today_empty(client):
    body = client.get("/api/today").json()
    assert body["members"] == []


def test_today_reflects_seeded_member_and_chore(client, parent_headers):
    _seed(client, parent_headers)
    body = client.get("/api/today").json()
    assert len(body["members"]) == 1
    m = body["members"][0]
    assert m["slug"] == "alice"
    assert m["today_progress_pct"] == 0
    assert len(m["instances"]) == 1
    assert m["instances"][0]["chore_name"] == "Dishes"
    assert m["instances"][0]["state"] == "pending"


# ─── complete / undo ──────────────────────────────────────────────────────


def test_complete_no_approval_awards_points(client, parent_headers):
    _, _, iid = _seed(client, parent_headers, points=7)
    r = client.post(f"/api/instances/{iid}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "done"
    assert body["points_awarded"] == 7


def test_complete_with_approval_parks_in_done_unapproved(client, parent_headers):
    _, _, iid = _seed(client, parent_headers, requires_approval=True, points=7)
    r = client.post(f"/api/instances/{iid}/complete")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "done_unapproved"
    assert body["points_awarded"] == 0


def test_complete_already_done_rejects(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    client.post(f"/api/instances/{iid}/complete")
    r = client.post(f"/api/instances/{iid}/complete")
    assert r.status_code == 409
    assert r.json()["error"] == "invalid_state"


def test_undo_within_window(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    client.post(f"/api/instances/{iid}/complete")
    r = client.post(f"/api/instances/{iid}/undo")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "pending"
    assert body["points_awarded"] == 0
    assert body["completed_at"] is None


def test_undo_without_complete_rejects(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    r = client.post(f"/api/instances/{iid}/undo")
    assert r.status_code == 409


def test_today_progress_updates_after_complete(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    client.post(f"/api/instances/{iid}/complete")
    body = client.get("/api/today").json()
    assert body["members"][0]["today_progress_pct"] == 100


# ─── approve / reject ─────────────────────────────────────────────────────


def test_approve_promotes_unapproved_to_done_and_awards_points(client, parent_headers):
    _, _, iid = _seed(client, parent_headers, requires_approval=True, points=7)
    client.post(f"/api/instances/{iid}/complete")
    r = client.post(f"/api/instances/{iid}/approve", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "done"
    assert body["points_awarded"] == 7
    assert body["approved_at"] is not None


def test_approve_without_parent_rejected(client, parent_headers):
    _, _, iid = _seed(client, parent_headers, requires_approval=True)
    client.post(f"/api/instances/{iid}/complete")
    r = client.post(f"/api/instances/{iid}/approve")
    assert r.status_code == 401


def test_approve_pending_rejected(client, parent_headers):
    _, _, iid = _seed(client, parent_headers, requires_approval=True)
    r = client.post(f"/api/instances/{iid}/approve", headers=parent_headers)
    assert r.status_code == 409


def test_reject_reverts_to_pending(client, parent_headers):
    _, _, iid = _seed(client, parent_headers, requires_approval=True)
    client.post(f"/api/instances/{iid}/complete")
    r = client.post(
        f"/api/instances/{iid}/reject",
        json={"reason": "too messy"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["state"] == "pending"
    assert r.json()["completed_at"] is None


# ─── skip ─────────────────────────────────────────────────────────────────


def test_skip_pending_instance(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    r = client.post(
        f"/api/instances/{iid}/skip",
        json={"reason": "sick"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["state"] == "skipped"


def test_skip_already_done_rejects(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    client.post(f"/api/instances/{iid}/complete")
    r = client.post(f"/api/instances/{iid}/skip", headers=parent_headers)
    assert r.status_code == 409


def test_skip_requires_parent(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    r = client.post(f"/api/instances/{iid}/skip")
    assert r.status_code == 401


# ─── points adjust ────────────────────────────────────────────────────────


def test_adjust_points_positive(client, parent_headers):
    alice_id, _, _ = _seed(client, parent_headers)
    r = client.post(
        f"/api/members/{alice_id}/points/adjust",
        json={"delta": 25, "reason": "birthday bonus"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["points_total"] == 25


def test_adjust_points_negative_clamps_at_zero(client, parent_headers):
    alice_id, _, _ = _seed(client, parent_headers)
    r = client.post(
        f"/api/members/{alice_id}/points/adjust",
        json={"delta": -50},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["points_total"] == 0


def test_adjust_points_requires_parent(client, parent_headers):
    alice_id, _, _ = _seed(client, parent_headers)
    r = client.post(f"/api/members/{alice_id}/points/adjust", json={"delta": 10})
    assert r.status_code == 401


def test_adjust_points_unknown_member_404(client, parent_headers):
    r = client.post(
        "/api/members/999/points/adjust",
        json={"delta": 10},
        headers=parent_headers,
    )
    assert r.status_code == 404


# ─── list / get ───────────────────────────────────────────────────────────


def test_list_instances_filter_by_member(client, parent_headers):
    alice_id, _, _ = _seed(client, parent_headers)
    r = client.get("/api/instances", params={"member_id": alice_id})
    assert r.status_code == 200
    assert all(inst["member_id"] == alice_id for inst in r.json())


def test_get_instance(client, parent_headers):
    _, _, iid = _seed(client, parent_headers)
    r = client.get(f"/api/instances/{iid}")
    assert r.status_code == 200
    assert r.json()["id"] == iid


def test_get_instance_404(client):
    r = client.get("/api/instances/999")
    assert r.status_code == 404
