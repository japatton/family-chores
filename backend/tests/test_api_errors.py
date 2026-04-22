"""Global error envelope + request-ID middleware."""

from __future__ import annotations


def test_error_envelope_shape_and_request_id_header(client):
    r = client.get("/api/members/ghost")
    assert r.status_code == 404
    body = r.json()
    assert set(body.keys()) == {"error", "detail", "request_id"}
    assert body["error"] == "not_found"
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_request_id_echoed_when_supplied(client):
    r = client.get("/api/members", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_request_id_generated_when_absent(client):
    r = client.get("/api/members")
    assert "X-Request-ID" in r.headers
    assert len(r.headers["X-Request-ID"]) >= 8


def test_validation_error_shape(client, parent_headers):
    # Missing required field "slug"
    r = client.post(
        "/api/members",
        json={"name": "A", "color": "#000", "display_mode": "kid_standard"},
        headers=parent_headers,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert "errors" in body
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_auth_required_shape(client):
    r = client.post("/api/admin/rebuild-stats")
    assert r.status_code == 401
    assert r.json()["error"] == "auth_required"
