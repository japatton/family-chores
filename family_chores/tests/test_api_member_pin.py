"""HTTP tests for the per-kid PIN endpoints (DECISIONS §17).

Covers GET /pin (status), POST /pin/set (parent), POST /pin/verify
(kid-friendly, no auth), POST /pin/clear (parent). Mirrors the parent-
PIN test patterns but on the per-member surface.
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
    assert r.status_code == 201
    return r.json()["id"]


# ─── GET /pin (status) ────────────────────────────────────────────────────


def test_pin_status_defaults_to_false_for_new_member(client, parent_headers):
    _member(client, parent_headers)
    r = client.get("/api/members/alice/pin")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "alice"
    assert body["pin_set"] is False


def test_pin_status_true_after_set(client, parent_headers):
    _member(client, parent_headers)
    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    r = client.get("/api/members/alice/pin")
    assert r.json()["pin_set"] is True


def test_pin_status_unknown_member_404(client):
    r = client.get("/api/members/ghost/pin")
    assert r.status_code == 404


# ─── POST /pin/set ────────────────────────────────────────────────────────


def test_pin_set_requires_parent(client, parent_headers):
    _member(client, parent_headers)
    r = client.post("/api/members/alice/pin/set", json={"pin": "1234"})
    assert r.status_code == 401


def test_pin_set_happy_path_returns_member_with_pin_set_true(
    client, parent_headers
):
    _member(client, parent_headers)
    r = client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "alice"
    assert body["pin_set"] is True
    # Hash itself must not appear in any response.
    assert "pin_hash" not in body


def test_pin_set_overwrites_existing_pin_without_current_pin(
    client, parent_headers
):
    """Per-kid PIN doesn't require proof-of-knowledge of the current PIN
    — parent already has elevated auth, and a forgotten kid PIN
    otherwise has no recovery path."""
    _member(client, parent_headers)
    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    r = client.post(
        "/api/members/alice/pin/set",
        json={"pin": "9999"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    # Old PIN no longer works.
    r1 = client.post("/api/members/alice/pin/verify", json={"pin": "1234"})
    assert r1.status_code == 401
    # New PIN works.
    r2 = client.post("/api/members/alice/pin/verify", json={"pin": "9999"})
    assert r2.status_code == 200


def test_pin_set_short_pin_422(client, parent_headers):
    _member(client, parent_headers)
    r = client.post(
        "/api/members/alice/pin/set",
        json={"pin": "12"},
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_pin_set_non_digit_422(client, parent_headers):
    _member(client, parent_headers)
    r = client.post(
        "/api/members/alice/pin/set",
        json={"pin": "abcd"},
        headers=parent_headers,
    )
    assert r.status_code == 422


# ─── POST /pin/verify ─────────────────────────────────────────────────────


def test_pin_verify_no_auth_required(client, parent_headers):
    _member(client, parent_headers)
    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    # No headers — verification is kid-facing.
    r = client.post("/api/members/alice/pin/verify", json={"pin": "1234"})
    assert r.status_code == 200
    body = r.json()
    assert body["member_id"] > 0
    assert body["verified_until"] > 0


def test_pin_verify_wrong_pin_401(client, parent_headers):
    _member(client, parent_headers)
    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    r = client.post("/api/members/alice/pin/verify", json={"pin": "9999"})
    assert r.status_code == 401


def test_pin_verify_no_pin_set_400(client, parent_headers):
    _member(client, parent_headers)
    r = client.post("/api/members/alice/pin/verify", json={"pin": "1234"})
    assert r.status_code == 400


def test_pin_verify_unknown_member_404(client):
    r = client.post("/api/members/ghost/pin/verify", json={"pin": "1234"})
    assert r.status_code == 404


# ─── POST /pin/clear ──────────────────────────────────────────────────────


def test_pin_clear_requires_parent(client, parent_headers):
    _member(client, parent_headers)
    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    r = client.post("/api/members/alice/pin/clear")
    assert r.status_code == 401


def test_pin_clear_happy_path(client, parent_headers):
    _member(client, parent_headers)
    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    r = client.post("/api/members/alice/pin/clear", headers=parent_headers)
    assert r.status_code == 200
    assert r.json()["pin_set"] is False
    # Verification on a cleared PIN returns 400 (PinNotSetError).
    r2 = client.post("/api/members/alice/pin/verify", json={"pin": "1234"})
    assert r2.status_code == 400


def test_pin_clear_idempotent(client, parent_headers):
    """Clearing an already-cleared PIN is a no-op success, not an error."""
    _member(client, parent_headers)
    r = client.post("/api/members/alice/pin/clear", headers=parent_headers)
    assert r.status_code == 200
    assert r.json()["pin_set"] is False


# ─── pin_set surfaces on MemberRead (existing GET /members) ───────────────


def test_pin_set_surfaces_on_member_read(client, parent_headers):
    _member(client, parent_headers)
    body = client.get("/api/members/alice").json()
    assert body["pin_set"] is False

    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    body = client.get("/api/members/alice").json()
    assert body["pin_set"] is True
    # Hash never exposed.
    assert "pin_hash" not in body


def test_pin_hash_never_in_member_list(client, parent_headers):
    _member(client, parent_headers)
    client.post(
        "/api/members/alice/pin/set",
        json={"pin": "1234"},
        headers=parent_headers,
    )
    body = client.get("/api/members").json()
    assert all("pin_hash" not in m for m in body)
    assert all("pin_set" in m for m in body)
