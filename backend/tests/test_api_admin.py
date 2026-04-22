"""HTTP tests for admin endpoints (rebuild stats, activity log)."""

from __future__ import annotations


def _seed_member(client, parent_headers, slug="alice") -> int:
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
    return r.json()["id"]


def test_rebuild_stats_requires_parent(client):
    r = client.post("/api/admin/rebuild-stats")
    assert r.status_code == 401


def test_rebuild_stats_counts_members(client, parent_headers):
    _seed_member(client, parent_headers, "alice")
    _seed_member(client, parent_headers, "bob")
    r = client.post("/api/admin/rebuild-stats", headers=parent_headers)
    assert r.status_code == 200
    assert r.json()["members_updated"] == 2


def test_activity_log_requires_parent(client):
    r = client.get("/api/admin/activity")
    assert r.status_code == 401


def test_activity_log_records_member_creates(client, parent_headers):
    _seed_member(client, parent_headers, "alice")
    _seed_member(client, parent_headers, "bob")

    r = client.get("/api/admin/activity", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    actions = [e["action"] for e in body["entries"]]
    # pin_set + two member_created, in reverse chronological order.
    assert actions.count("member_created") == 2
    assert "pin_set" in actions


def test_activity_log_pagination(client, parent_headers):
    for i in range(5):
        _seed_member(client, parent_headers, f"kid{i}")

    page1 = client.get(
        "/api/admin/activity",
        params={"limit": 2, "offset": 0},
        headers=parent_headers,
    ).json()
    page2 = client.get(
        "/api/admin/activity",
        params={"limit": 2, "offset": 2},
        headers=parent_headers,
    ).json()

    assert len(page1["entries"]) == 2
    assert len(page2["entries"]) == 2
    assert page1["entries"][0]["id"] != page2["entries"][0]["id"]
    assert page1["total"] == page2["total"] >= 6


def test_activity_log_filter_by_action(client, parent_headers):
    _seed_member(client, parent_headers, "alice")
    r = client.get(
        "/api/admin/activity",
        params={"action": "member_created"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert all(e["action"] == "member_created" for e in entries)
