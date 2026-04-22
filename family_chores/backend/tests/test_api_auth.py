"""HTTP tests for the parent-PIN + JWT flow."""

from __future__ import annotations

import time

import jwt


def test_whoami_anonymous_no_pin_set(client):
    r = client.get("/api/auth/whoami")
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == "anonymous"
    assert body["parent_pin_set"] is False
    assert body["parent_mode_active"] is False


def test_whoami_honours_x_remote_user(client):
    r = client.get("/api/auth/whoami", headers={"X-Remote-User": "jason"})
    assert r.json()["user"] == "jason"


def test_set_pin_first_time(client):
    r = client.post("/api/auth/pin/set", json={"pin": "1234"})
    assert r.status_code == 200
    assert r.json()["parent_pin_set"] is True

    who = client.get("/api/auth/whoami").json()
    assert who["parent_pin_set"] is True


def test_set_pin_rotation_requires_current_pin(client):
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    r = client.post("/api/auth/pin/set", json={"pin": "5678"})
    assert r.status_code == 400
    assert r.json()["error"] == "pin_already_set"


def test_set_pin_rotation_with_wrong_current(client):
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    r = client.post("/api/auth/pin/set", json={"pin": "5678", "current_pin": "0000"})
    assert r.status_code == 401
    assert r.json()["error"] == "pin_invalid"


def test_set_pin_rotation_with_correct_current(client):
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    r = client.post("/api/auth/pin/set", json={"pin": "5678", "current_pin": "1234"})
    assert r.status_code == 200

    # Old PIN no longer works, new one does
    r = client.post("/api/auth/pin/verify", json={"pin": "1234"})
    assert r.status_code == 401
    r = client.post("/api/auth/pin/verify", json={"pin": "5678"})
    assert r.status_code == 200


def test_verify_pin_returns_short_lived_jwt(client):
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    r = client.post("/api/auth/pin/verify", json={"pin": "1234"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["token"], str) and len(body["token"]) > 40
    now = int(time.time())
    # JWT TTL is 5 minutes — expires_at should be within (now, now+310].
    assert now < body["expires_at"] <= now + 310


def test_verify_pin_wrong_returns_401(client):
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    r = client.post("/api/auth/pin/verify", json={"pin": "9999"})
    assert r.status_code == 401
    assert r.json()["error"] == "pin_invalid"


def test_verify_pin_without_pin_set_returns_400(client):
    r = client.post("/api/auth/pin/verify", json={"pin": "1234"})
    assert r.status_code == 400
    assert r.json()["error"] == "pin_not_set"


def test_refresh_extends_parent_session(client, parent_headers):
    r = client.post("/api/auth/refresh", headers=parent_headers)
    assert r.status_code == 200
    new_token = r.json()["token"]
    # Fresh token still grants refresh
    r = client.post(
        "/api/auth/refresh", headers={"Authorization": f"Bearer {new_token}"}
    )
    assert r.status_code == 200


def test_refresh_without_token_rejected(client):
    r = client.post("/api/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"] == "auth_required"


def test_refresh_with_expired_token_rejected(client):
    # Mint an already-expired parent token with the app's secret.
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    secret = client.app.state.jwt_secret
    expired = jwt.encode(
        {"sub": "test", "role": "parent", "iat": 0, "exp": 1},
        secret,
        algorithm="HS256",
    )
    r = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_refresh_with_wrong_role_rejected(client):
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    secret = client.app.state.jwt_secret
    import time as _t
    bad = jwt.encode(
        {"sub": "kid", "role": "kid", "iat": int(_t.time()), "exp": int(_t.time()) + 60},
        secret,
        algorithm="HS256",
    )
    r = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_whoami_reports_parent_mode_active_with_token(client, parent_headers):
    r = client.get("/api/auth/whoami", headers=parent_headers)
    body = r.json()
    assert body["parent_mode_active"] is True
    assert body["parent_pin_set"] is True


def test_clear_pin_requires_correct_pin(client):
    client.post("/api/auth/pin/set", json={"pin": "1234"})
    r = client.post("/api/auth/pin/clear", json={"pin": "0000"})
    assert r.status_code == 401
    r = client.post("/api/auth/pin/clear", json={"pin": "1234"})
    assert r.status_code == 200
    assert r.json()["parent_pin_set"] is False


def test_clear_pin_when_not_set(client):
    r = client.post("/api/auth/pin/clear", json={"pin": "1234"})
    assert r.status_code == 400
    assert r.json()["error"] == "pin_not_set"


def test_pin_format_validation(client):
    # Too short
    r = client.post("/api/auth/pin/set", json={"pin": "12"})
    assert r.status_code == 422
    # Non-numeric
    r = client.post("/api/auth/pin/set", json={"pin": "abcd"})
    assert r.status_code == 422
