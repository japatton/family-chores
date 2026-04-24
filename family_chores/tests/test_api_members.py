"""HTTP tests for member CRUD + parent-mode enforcement."""

from __future__ import annotations


def _new_member_body(slug="alice", **over):
    return {
        "name": over.get("name", slug.title()),
        "slug": slug,
        "avatar": over.get("avatar"),
        "color": over.get("color", "#ff0000"),
        "display_mode": over.get("display_mode", "kid_standard"),
        "requires_approval": over.get("requires_approval", False),
    }


def test_list_members_empty(client):
    r = client.get("/api/members")
    assert r.status_code == 200
    assert r.json() == []


def test_create_member_requires_parent(client):
    r = client.post("/api/members", json=_new_member_body())
    assert r.status_code == 401
    assert r.json()["error"] == "auth_required"


def test_create_member_happy_path(client, parent_headers):
    r = client.post("/api/members", json=_new_member_body(), headers=parent_headers)
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "alice"
    assert body["stats"]["points_total"] == 0


def test_create_member_duplicate_slug_rejected(client, parent_headers):
    client.post("/api/members", json=_new_member_body(), headers=parent_headers)
    r = client.post("/api/members", json=_new_member_body(), headers=parent_headers)
    assert r.status_code == 409
    assert r.json()["error"] == "conflict"


def test_get_member_not_found(client):
    r = client.get("/api/members/ghost")
    assert r.status_code == 404
    assert r.json()["error"] == "not_found"


def test_patch_member_requires_parent(client, parent_headers):
    client.post("/api/members", json=_new_member_body(), headers=parent_headers)
    r = client.patch("/api/members/alice", json={"color": "#00ff00"})
    assert r.status_code == 401


def test_patch_member_partial_update(client, parent_headers):
    client.post("/api/members", json=_new_member_body(), headers=parent_headers)
    r = client.patch(
        "/api/members/alice",
        json={"color": "#00ff00", "requires_approval": True},
        headers=parent_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["color"] == "#00ff00"
    assert body["requires_approval"] is True
    assert body["name"] == "Alice"  # unchanged


def test_patch_missing_member_404(client, parent_headers):
    r = client.patch("/api/members/ghost", json={"color": "#fff"}, headers=parent_headers)
    assert r.status_code == 404


def test_delete_member_requires_parent(client, parent_headers):
    client.post("/api/members", json=_new_member_body(), headers=parent_headers)
    r = client.delete("/api/members/alice")
    assert r.status_code == 401
    r = client.delete("/api/members/alice", headers=parent_headers)
    assert r.status_code == 204


def test_delete_member_cascades_in_db(client, parent_headers):
    client.post("/api/members", json=_new_member_body(), headers=parent_headers)
    # Create a chore assigned to alice
    chore_body = {
        "name": "Dishes",
        "points": 5,
        "recurrence_type": "daily",
        "recurrence_config": {},
        "assigned_member_ids": [
            client.get("/api/members/alice").json()["id"],
        ],
    }
    client.post("/api/chores", json=chore_body, headers=parent_headers)

    client.delete("/api/members/alice", headers=parent_headers)

    # GET members → empty
    assert client.get("/api/members").json() == []
    # Chore still exists but has no assignees
    chore = client.get("/api/chores").json()[0]
    assert chore["assigned_member_ids"] == []


def test_slug_validation(client, parent_headers):
    for bad in ("Alice", "alice!", "has space", ""):
        r = client.post(
            "/api/members",
            json={
                "name": "A",
                "slug": bad,
                "color": "#000000",
                "display_mode": "kid_standard",
                "requires_approval": False,
            },
            headers=parent_headers,
        )
        assert r.status_code == 422, f"expected 422 for slug={bad!r}"
