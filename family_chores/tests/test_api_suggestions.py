"""HTTP tests for /api/suggestions/* (DECISIONS §13 step 5).

Uses the addon's full TestClient (lifespan-bootstrapped DB with the 46
starter templates already seeded). Most tests run against the default
single-tenant scope; the tenant-isolation test overrides
`get_auth_strategy` to flip between two synthetic households (mirrors
the pattern in `test_household_scoping.py`).

Companion seeder tests (real-DB, no HTTP) live in
`family_chores/tests/test_seeding.py`.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from family_chores_api.deps.auth import Identity, ParentIdentity, get_auth_strategy
from family_chores_api.errors import AuthRequiredError
from fastapi import Request
from fastapi.testclient import TestClient

from family_chores_addon.app import create_app

# ─── starter library size — pinned by the bundled JSON ────────────────────


STARTER_COUNT = 46


# ─── list ─────────────────────────────────────────────────────────────────


def test_list_requires_parent(client):
    """No bearer token = 401."""
    assert client.get("/api/suggestions").status_code == 401


def test_list_starter_seeded_returns_46(client, parent_headers):
    """Lifespan seeded the bundled library; default list returns all."""
    r = client.get("/api/suggestions", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == STARTER_COUNT
    assert all(s["source"] == "starter" for s in body)


def test_list_filtered_by_category_kitchen_returns_8(client, parent_headers):
    """Eight kitchen entries per the bundled library."""
    r = client.get("/api/suggestions?category=kitchen", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 8
    assert all(s["category"] == "kitchen" for s in body)


def test_list_filtered_by_age_4_excludes_higher_age_min(client, parent_headers):
    """age=4 should match entries with age_min<=4 (and age_max NULL or >=4)."""
    r = client.get("/api/suggestions?age=4", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    # Library entries with age_min in {3, 4} should match. Entries with
    # age_min in {6, 8, 10} should NOT match.
    assert all(s["age_min"] is None or s["age_min"] <= 4 for s in body)
    assert not any(s["age_min"] == 8 for s in body)


def test_list_source_starter_only(client, parent_headers):
    r = client.get("/api/suggestions?source=starter", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == STARTER_COUNT
    assert {s["source"] for s in body} == {"starter"}


def test_list_source_custom_only_when_no_custom_yet(client, parent_headers):
    r = client.get("/api/suggestions?source=custom", headers=parent_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_source_invalid_returns_409(client, parent_headers):
    r = client.get("/api/suggestions?source=bogus", headers=parent_headers)
    assert r.status_code == 409


def test_list_q_substring_search_case_insensitive(client, parent_headers):
    """Two starter names contain 'bed': 'Make bed' and 'Tidy bedroom'."""
    r = client.get("/api/suggestions?q=BED", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    names = sorted(s["name"] for s in body)
    assert "Make bed" in names
    assert "Tidy bedroom" in names


# ─── get ──────────────────────────────────────────────────────────────────


def test_get_returns_template(client, parent_headers):
    body = client.get("/api/suggestions", headers=parent_headers).json()
    target_id = body[0]["id"]

    r = client.get(f"/api/suggestions/{target_id}", headers=parent_headers)
    assert r.status_code == 200
    assert r.json()["id"] == target_id


def test_get_unknown_id_returns_404(client, parent_headers):
    r = client.get("/api/suggestions/no-such-id", headers=parent_headers)
    assert r.status_code == 404


# ─── create ───────────────────────────────────────────────────────────────


def _suggestion_body(name="Custom chore", **over) -> dict:
    body = {
        "name": name,
        "icon": "mdi:test",
        "category": "other",
        "age_min": 6,
        "age_max": None,
        "points_suggested": 3,
        "default_recurrence_type": "daily",
        "default_recurrence_config": {},
        "description": "test description",
    }
    body.update(over)
    return body


def test_post_requires_parent(client):
    r = client.post("/api/suggestions", json=_suggestion_body())
    assert r.status_code == 401


def test_post_creates_custom_suggestion(client, parent_headers):
    r = client.post(
        "/api/suggestions", json=_suggestion_body(), headers=parent_headers
    )
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "custom"
    assert body["starter_key"] is None
    assert body["name"] == "Custom chore"
    assert body["points_suggested"] == 3


def test_post_dedup_returns_409_with_existing_id(client, parent_headers):
    """Creating the same name twice — second returns 409 + existing_id."""
    first = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Sweep porch"),
        headers=parent_headers,
    )
    assert first.status_code == 201
    first_id = first.json()["id"]

    second = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="sweep PORCH."),  # normalizes to same key
        headers=parent_headers,
    )
    assert second.status_code == 409
    assert second.json()["existing_id"] == first_id


def test_post_dedup_against_starter_library(client, parent_headers):
    """Trying to create a custom suggestion that collides with a seeded
    starter (e.g. 'Make bed') also returns 409 — same dedup table."""
    starters = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()
    make_bed = next(s for s in starters if s["name"] == "Make bed")

    r = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Make bed."),
        headers=parent_headers,
    )
    assert r.status_code == 409
    assert r.json()["existing_id"] == make_bed["id"]


def test_post_invalid_recurrence_config_422(client, parent_headers):
    """Pydantic-layer validation fires before the dedup check."""
    r = client.post(
        "/api/suggestions",
        json=_suggestion_body(
            default_recurrence_type="every_n_days", default_recurrence_config={}
        ),
        headers=parent_headers,
    )
    assert r.status_code == 422


# ─── patch ────────────────────────────────────────────────────────────────


def test_patch_custom_template(client, parent_headers):
    created = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Patchable"),
        headers=parent_headers,
    ).json()

    r = client.patch(
        f"/api/suggestions/{created['id']}",
        json={"points_suggested": 99},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["points_suggested"] == 99


def test_patch_starter_name_immutable_409(client, parent_headers):
    starter_id = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()[0]["id"]

    r = client.patch(
        f"/api/suggestions/{starter_id}",
        json={"name": "Renamed starter"},
        headers=parent_headers,
    )
    assert r.status_code == 409


def test_patch_starter_other_fields_editable(client, parent_headers):
    """A parent can bump points or change icon on a starter — only `name`
    is locked down."""
    starter = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()[0]

    r = client.patch(
        f"/api/suggestions/{starter['id']}",
        json={"points_suggested": 999, "icon": "mdi:custom-icon"},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["points_suggested"] == 999
    assert r.json()["icon"] == "mdi:custom-icon"


def test_patch_dedup_returns_409_with_existing_id(client, parent_headers):
    """Renaming a custom template to a name another template already has
    fires the same 409+existing_id flow as POST."""
    a = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Original A"),
        headers=parent_headers,
    ).json()
    b = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Original B"),
        headers=parent_headers,
    ).json()

    r = client.patch(
        f"/api/suggestions/{b['id']}",
        json={"name": "ORIGINAL a"},
        headers=parent_headers,
    )
    assert r.status_code == 409
    assert r.json()["existing_id"] == a["id"]


# ─── delete ───────────────────────────────────────────────────────────────


def test_delete_custom_hard_deletes(client, parent_headers):
    created = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Delete me"),
        headers=parent_headers,
    ).json()

    r = client.delete(
        f"/api/suggestions/{created['id']}", headers=parent_headers
    )
    assert r.status_code == 204

    assert (
        client.get(
            f"/api/suggestions/{created['id']}", headers=parent_headers
        ).status_code
        == 404
    )


def test_delete_starter_then_reseed_does_not_re_create(client, parent_headers):
    """Soft-delete: deleting a starter inserts a suppression so the
    seeder skips it on subsequent runs. Verified via `/api/suggestions/reset`
    showing zero re-seeded entries until we clear suppression."""
    starters = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()
    target = next(s for s in starters if s["name"] == "Make bed")

    assert (
        client.delete(
            f"/api/suggestions/{target['id']}", headers=parent_headers
        ).status_code
        == 204
    )

    # The deleted starter must NOT come back via list now.
    after = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()
    assert not any(s["id"] == target["id"] for s in after)
    assert not any(s["name"] == "Make bed" for s in after)


# ─── reset ────────────────────────────────────────────────────────────────


def test_reset_with_no_suppressions_is_noop(client, parent_headers):
    r = client.post("/api/suggestions/reset", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["suppressions_cleared"] == 0
    assert body["seeded"] == 0
    assert body["library_version"] >= 1


def test_reset_clears_suppression_and_reseeds(client, parent_headers):
    """End-to-end: delete a starter, confirm it's gone, reset, confirm
    it's back."""
    starters = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()
    target = next(s for s in starters if s["name"] == "Make bed")

    client.delete(f"/api/suggestions/{target['id']}", headers=parent_headers)

    r = client.post("/api/suggestions/reset", headers=parent_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["suppressions_cleared"] == 1
    assert body["seeded"] == 1

    after = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()
    assert any(s["name"] == "Make bed" for s in after)


# ─── tenant isolation (DECISIONS §13 §1.1, §11 step 9) ────────────────────


@dataclass
class _FakeAuth:
    """Inline fake — same shape as test_household_scoping.py's helper."""

    user_key: str = "tester"
    household_id: str | None = None
    is_parent: bool = True

    async def identify(self, request: Request) -> Identity:
        return Identity(
            user_key=self.user_key,
            household_id=self.household_id,
            is_parent=self.is_parent,
        )

    async def require_parent(self, request: Request) -> ParentIdentity:
        if not self.is_parent:
            raise AuthRequiredError("parent mode required")
        return ParentIdentity(
            user_key=self.user_key,
            household_id=self.household_id,
            expires_at=int(time.time()) + 600,
        )


@pytest.fixture
def two_household_client(api_options, monkeypatch) -> Iterator[TestClient]:
    """A TestClient with the lifespan run AND `get_auth_strategy` overridden
    so each request can be flipped between household-a and household-b."""
    monkeypatch.setenv("FAMILY_CHORES_SKIP_SCHEDULER", "1")
    app = create_app(options=api_options)
    auth = _FakeAuth(household_id="household-a")
    app.dependency_overrides[get_auth_strategy] = lambda: auth
    with TestClient(app) as c:
        yield c, auth


def test_household_a_does_not_see_household_b_custom_suggestions(
    two_household_client,
):
    client, auth = two_household_client

    # Create custom-A.
    auth.household_id = "household-a"
    a_id = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Custom A"),
    ).json()["id"]

    # Create custom-B.
    auth.household_id = "household-b"
    b_id = client.post(
        "/api/suggestions",
        json=_suggestion_body(name="Custom B"),
    ).json()["id"]

    # household-a sees only its own custom.
    auth.household_id = "household-a"
    a_customs = client.get("/api/suggestions?source=custom").json()
    assert {s["id"] for s in a_customs} == {a_id}

    # household-b sees only its own custom.
    auth.household_id = "household-b"
    b_customs = client.get("/api/suggestions?source=custom").json()
    assert {s["id"] for s in b_customs} == {b_id}

    # Cross-household GET by id is 404, not 200.
    auth.household_id = "household-a"
    r = client.get(f"/api/suggestions/{b_id}")
    assert r.status_code == 404
