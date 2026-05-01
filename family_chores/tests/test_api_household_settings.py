"""HTTP tests for `/api/household/settings` (DECISIONS §14)."""

from __future__ import annotations


def test_get_settings_returns_default_for_fresh_household(client):
    """No row materialised yet → empty defaults, no 404."""
    r = client.get("/api/household/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["shared_calendar_entity_ids"] == []
    assert body["updated_at"] is None


def test_put_settings_requires_parent(client):
    r = client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": ["calendar.family"]},
    )
    assert r.status_code == 401
    assert r.json()["error"] == "auth_required"


def test_put_settings_persists_and_dedupes(client, parent_headers):
    r = client.put(
        "/api/household/settings",
        json={
            "shared_calendar_entity_ids": [
                "calendar.family",
                "calendar.school",
                "calendar.family",  # duplicate — should dedupe
                "  calendar.sports  ",  # whitespace — should strip
                "",  # empty — should drop
            ]
        },
        headers=parent_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shared_calendar_entity_ids"] == [
        "calendar.family",
        "calendar.school",
        "calendar.sports",
    ]
    assert body["updated_at"] is not None

    # Second GET reflects the persisted state.
    r2 = client.get("/api/household/settings")
    assert r2.status_code == 200
    assert r2.json()["shared_calendar_entity_ids"] == [
        "calendar.family",
        "calendar.school",
        "calendar.sports",
    ]


def test_put_settings_rejects_non_calendar_entity(client, parent_headers):
    r = client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": ["sensor.kitchen"]},
        headers=parent_headers,
    )
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"


def test_put_settings_partial_update_leaves_other_fields(client, parent_headers):
    """Setting `shared_calendar_entity_ids = None` is a no-op (the
    field's omission would behave the same in this single-field
    schema, but verifying an explicit None ignores)."""
    # Establish baseline.
    client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": ["calendar.family"]},
        headers=parent_headers,
    )
    # Now PUT with explicit None — should leave the existing value alone.
    r = client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": None},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["shared_calendar_entity_ids"] == ["calendar.family"]


def test_put_settings_clear_with_empty_list(client, parent_headers):
    """An empty list (not None) is the explicit "clear all" intent."""
    client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": ["calendar.family"]},
        headers=parent_headers,
    )
    r = client.put(
        "/api/household/settings",
        json={"shared_calendar_entity_ids": []},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["shared_calendar_entity_ids"] == []
