"""HTTP tests for /api/rewards and the redemption flow.

Covers:
  - Reward CRUD + parent-required gating + active/inactive filtering.
  - Kid-facing redeem path: success, insufficient balance, weekly cap.
  - Parent approve / deny: state machine, refund on deny, audit fields.
  - Snapshot fields hold across reward edits.
"""

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
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _give_points(client, parent_headers, member_id: int, points: int) -> None:
    r = client.post(
        f"/api/members/{member_id}/points/adjust",
        json={"delta": points, "reason": "test seeding"},
        headers=parent_headers,
    )
    assert r.status_code == 200, r.text


def _reward_body(name="Ice cream", cost=50, **over) -> dict:
    body = {
        "name": name,
        "description": "A small bowl",
        "cost_points": cost,
        "icon": "mdi:ice-cream",
        "active": True,
    }
    body.update(over)
    return body


# ─── reward CRUD ──────────────────────────────────────────────────────────


def test_list_rewards_empty(client):
    """Kid-visible — no auth required."""
    r = client.get("/api/rewards")
    assert r.status_code == 200
    assert r.json() == []


def test_create_reward_requires_parent(client):
    r = client.post("/api/rewards", json=_reward_body())
    assert r.status_code == 401


def test_create_reward_happy_path(client, parent_headers):
    r = client.post("/api/rewards", json=_reward_body(), headers=parent_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Ice cream"
    assert body["cost_points"] == 50
    assert body["active"] is True


def test_create_reward_zero_cost_422(client, parent_headers):
    r = client.post(
        "/api/rewards",
        json=_reward_body(cost=0),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_create_reward_negative_cost_422(client, parent_headers):
    r = client.post(
        "/api/rewards",
        json=_reward_body(cost=-5),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_list_rewards_default_filters_to_active(client, parent_headers):
    """Soft-deleted rewards are hidden by default — kid catalogue is
    active-only."""
    a = client.post("/api/rewards", json=_reward_body("Active"), headers=parent_headers).json()
    b = client.post(
        "/api/rewards",
        json=_reward_body("Retired", active=False),
        headers=parent_headers,
    ).json()

    listed = client.get("/api/rewards").json()
    ids = {r["id"] for r in listed}
    assert a["id"] in ids
    assert b["id"] not in ids


def test_list_rewards_active_false_returns_inactive_only(client, parent_headers):
    a = client.post("/api/rewards", json=_reward_body("Active"), headers=parent_headers).json()
    b = client.post(
        "/api/rewards",
        json=_reward_body("Retired", active=False),
        headers=parent_headers,
    ).json()

    inactive = client.get("/api/rewards?active=false").json()
    ids = {r["id"] for r in inactive}
    assert b["id"] in ids
    assert a["id"] not in ids


def test_patch_reward(client, parent_headers):
    created = client.post(
        "/api/rewards", json=_reward_body(), headers=parent_headers
    ).json()
    r = client.patch(
        f"/api/rewards/{created['id']}",
        json={"cost_points": 100, "name": "Big ice cream"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["cost_points"] == 100
    assert r.json()["name"] == "Big ice cream"


def test_delete_reward_soft_deletes(client, parent_headers):
    created = client.post(
        "/api/rewards", json=_reward_body(), headers=parent_headers
    ).json()
    r = client.delete(f"/api/rewards/{created['id']}", headers=parent_headers)
    assert r.status_code == 204
    # Active list no longer includes it.
    assert created["id"] not in {r["id"] for r in client.get("/api/rewards").json()}
    # But it's still readable directly (active=False).
    body = client.get(f"/api/rewards/{created['id']}").json()
    assert body["active"] is False


# ─── kid-facing redeem ────────────────────────────────────────────────────


def test_redeem_insufficient_balance_409(client, parent_headers):
    _member(client, parent_headers)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=100), headers=parent_headers
    ).json()
    # Member has 0 points.
    r = client.post(
        "/api/members/alice/redemptions",
        json={"reward_id": reward["id"]},
    )
    assert r.status_code == 409


def test_redeem_happy_path_deducts_points(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=30), headers=parent_headers
    ).json()

    r = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "pending_approval"
    assert body["cost_points_at_redeem"] == 30
    assert body["reward_name_at_redeem"] == "Ice cream"

    # Member's points dropped by 30 immediately.
    member = client.get("/api/members/alice").json()
    assert member["stats"]["points_total"] == 70


def test_redeem_against_inactive_reward_409(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(active=False), headers=parent_headers
    ).json()
    r = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    )
    assert r.status_code == 409


def test_redeem_unknown_reward_404(client, parent_headers):
    _member(client, parent_headers)
    r = client.post(
        "/api/members/alice/redemptions",
        json={"reward_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


def test_redeem_weekly_cap_enforced(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 1000)
    reward = client.post(
        "/api/rewards",
        json=_reward_body(cost=10, max_per_week=2),
        headers=parent_headers,
    ).json()

    r1 = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    )
    r2 = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    )
    r3 = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r3.status_code == 409  # cap reached


# ─── parent approve / deny ────────────────────────────────────────────────


def test_pending_queue_lists_pending_approval(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=10), headers=parent_headers
    ).json()
    client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    )
    listed = client.get(
        "/api/redemptions?state=pending_approval", headers=parent_headers
    ).json()
    assert len(listed) == 1
    assert listed[0]["state"] == "pending_approval"


def test_approve_requires_parent(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=10), headers=parent_headers
    ).json()
    r = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()
    response = client.post(f"/api/redemptions/{r['id']}/approve")
    assert response.status_code == 401


def test_approve_happy_path_no_points_change(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=30), headers=parent_headers
    ).json()
    redemption = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()

    # After redeem: 70 points.
    pre_approve = client.get("/api/members/alice").json()
    assert pre_approve["stats"]["points_total"] == 70

    r = client.post(
        f"/api/redemptions/{redemption['id']}/approve", headers=parent_headers
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "approved"
    assert body["approved_by"]
    assert body["approved_at"]

    # Approve doesn't move points.
    after_approve = client.get("/api/members/alice").json()
    assert after_approve["stats"]["points_total"] == 70


def test_approve_already_approved_returns_409(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=10), headers=parent_headers
    ).json()
    redemption = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()
    client.post(
        f"/api/redemptions/{redemption['id']}/approve", headers=parent_headers
    )
    r = client.post(
        f"/api/redemptions/{redemption['id']}/approve", headers=parent_headers
    )
    assert r.status_code == 409


def test_deny_refunds_points(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=30), headers=parent_headers
    ).json()
    redemption = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()
    # After redeem: 70 points.
    assert client.get("/api/members/alice").json()["stats"]["points_total"] == 70

    r = client.post(
        f"/api/redemptions/{redemption['id']}/deny",
        json={"reason": "Not earned"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "denied"
    assert body["denied_reason"] == "Not earned"
    assert body["denied_by"]
    assert body["denied_at"]

    # Deny refunds the cost back to 100.
    after_deny = client.get("/api/members/alice").json()
    assert after_deny["stats"]["points_total"] == 100


def test_deny_already_denied_returns_409(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=10), headers=parent_headers
    ).json()
    redemption = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()
    client.post(
        f"/api/redemptions/{redemption['id']}/deny",
        json={"reason": "Nope"},
        headers=parent_headers,
    )
    r = client.post(
        f"/api/redemptions/{redemption['id']}/deny",
        json={"reason": "Nope again"},
        headers=parent_headers,
    )
    assert r.status_code == 409


# ─── snapshot fields ──────────────────────────────────────────────────────


def test_redemption_snapshot_survives_reward_rename(client, parent_headers):
    """Renaming/repricing a reward must not retroactively change
    historical redemptions — they hold cost_points_at_redeem and
    reward_name_at_redeem snapshots."""
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards",
        json=_reward_body(name="Original Reward", cost=30),
        headers=parent_headers,
    ).json()
    redemption = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()

    # Parent renames + reprices the reward.
    client.patch(
        f"/api/rewards/{reward['id']}",
        json={"name": "Renamed Reward", "cost_points": 999},
        headers=parent_headers,
    )

    # Redemption row preserves the original.
    r = client.get(
        "/api/members/alice/redemptions"
    ).json()
    assert len(r) == 1
    assert r[0]["reward_name_at_redeem"] == "Original Reward"
    assert r[0]["cost_points_at_redeem"] == 30
    # Confirm by fetching by id.
    assert r[0]["id"] == redemption["id"]


# ─── member redemption history ────────────────────────────────────────────


def test_member_redemptions_lists_newest_first(client, parent_headers):
    member_id = _member(client, parent_headers)
    _give_points(client, parent_headers, member_id, 100)
    reward = client.post(
        "/api/rewards", json=_reward_body(cost=10), headers=parent_headers
    ).json()
    a = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()
    b = client.post(
        "/api/members/alice/redemptions", json={"reward_id": reward["id"]}
    ).json()
    listed = client.get("/api/members/alice/redemptions").json()
    assert [r["id"] for r in listed] == [b["id"], a["id"]]


def test_member_redemptions_unknown_member_404(client):
    r = client.get("/api/members/ghost/redemptions")
    assert r.status_code == 404
