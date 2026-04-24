"""Smoke tests for the SaaS scaffold.

The SaaS deployment target is a Phase 3 placeholder. All these tests
prove is the wiring works end-to-end: `create_app()` produces a real
FastAPI instance, the health endpoint is reachable, and every tenant-
scoped route correctly bounces with HTTP 501 because
`PlaceholderAuthStrategy.identify` raises during dep resolution.

These tests double as regression catchers for the
`family_chores_api.create_app` factory's deployment-target-agnosticism:
if a future router or dep starts implicitly assuming the addon's
`IngressAuthStrategy`, the saas scaffold will fail one of these tests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from family_chores_saas import __version__, create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_package_importable() -> None:
    assert __version__ == "0.1.0"


def test_health_returns_200(client: TestClient) -> None:
    """`/api/health` is the only endpoint that doesn't depend on auth."""
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/members"),
        ("POST", "/api/members"),
        ("GET", "/api/chores"),
        ("POST", "/api/chores"),
        ("GET", "/api/instances"),
        ("GET", "/api/today"),
        ("POST", "/api/admin/rebuild-stats"),
        ("GET", "/api/admin/activity"),
        ("GET", "/api/auth/whoami"),
        ("POST", "/api/auth/pin/set"),
    ],
)
def test_tenant_scoped_endpoint_returns_501(
    client: TestClient, method: str, path: str
) -> None:
    """Every route that touches `Depends(get_session)` /
    `Depends(get_remote_user)` / `Depends(get_current_household_id)`
    flows through the `AuthStrategy` first — `PlaceholderAuthStrategy`
    raises HTTPException(501), so the response is 501 regardless of
    request body shape."""
    r = client.request(method, path, json={})
    assert r.status_code == 501, (
        f"{method} {path} returned {r.status_code} {r.text!r}; expected 501 "
        f"(PlaceholderAuthStrategy should have raised before any other dep "
        f"could run)"
    )
