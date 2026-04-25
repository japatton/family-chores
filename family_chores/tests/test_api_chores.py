"""HTTP tests for chore CRUD + recurrence-config validation."""

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


def _chore_body(name="Dishes", members=None, **over):
    body = {
        "name": name,
        "points": 5,
        "active": True,
        "recurrence_type": "daily",
        "recurrence_config": {},
        "assigned_member_ids": members or [],
    }
    body.update(over)
    return body


def test_list_chores_empty(client):
    assert client.get("/api/chores").json() == []


def test_create_chore_requires_parent(client):
    r = client.post("/api/chores", json=_chore_body())
    assert r.status_code == 401


def test_create_chore_happy_path(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Dishes"
    assert body["assigned_member_ids"] == [alice_id]


def test_create_chore_unknown_member_404(client, parent_headers):
    r = client.post(
        "/api/chores", json=_chore_body(members=[999]), headers=parent_headers
    )
    assert r.status_code == 404


def test_create_chore_with_valid_specific_days_config(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="specific_days",
            recurrence_config={"days": [1, 3, 5]},
        ),
        headers=parent_headers,
    )
    assert r.status_code == 201
    assert r.json()["recurrence_config"] == {"days": [1, 3, 5]}


def test_create_chore_with_invalid_specific_days_422(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="specific_days",
            recurrence_config={"days": [0, 9]},  # invalid ISO weekdays
        ),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_create_chore_monthly_31_accepted(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="monthly_on_date", recurrence_config={"day": 31}
        ),
        headers=parent_headers,
    )
    assert r.status_code == 201


def test_create_chore_monthly_invalid_day_422(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="monthly_on_date", recurrence_config={"day": 32}
        ),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_create_chore_once_requires_date(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(recurrence_type="once", recurrence_config={}),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_every_n_days_requires_anchor(client, parent_headers):
    r = client.post(
        "/api/chores",
        json=_chore_body(
            recurrence_type="every_n_days", recurrence_config={"n": 3}
        ),
        headers=parent_headers,
    )
    assert r.status_code == 422


def test_patch_chore(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    chore_id = r.json()["id"]
    r = client.patch(
        f"/api/chores/{chore_id}",
        json={"points": 20, "active": False},
        headers=parent_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["points"] == 20
    assert body["active"] is False


def test_patch_chore_changes_assignments(client, parent_headers):
    alice_id = _member(client, parent_headers, "alice")
    bob_id = _member(client, parent_headers, "bob")
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    chore_id = r.json()["id"]
    r = client.patch(
        f"/api/chores/{chore_id}",
        json={"assigned_member_ids": [bob_id]},
        headers=parent_headers,
    )
    assert r.status_code == 200
    assert r.json()["assigned_member_ids"] == [bob_id]


def test_delete_chore_cascades_instances(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores", json=_chore_body(members=[alice_id]), headers=parent_headers
    )
    chore_id = r.json()["id"]

    # Today's instance should exist (create_chore triggers generate_instances)
    today = client.get("/api/today").json()
    assert len(today["members"][0]["instances"]) == 1

    assert client.delete(f"/api/chores/{chore_id}", headers=parent_headers).status_code == 204

    today = client.get("/api/today").json()
    assert today["members"][0]["instances"] == []


def test_list_chores_filter_by_member(client, parent_headers):
    alice_id = _member(client, parent_headers, "alice")
    bob_id = _member(client, parent_headers, "bob")
    client.post(
        "/api/chores",
        json=_chore_body("Dishes", members=[alice_id]),
        headers=parent_headers,
    )
    client.post(
        "/api/chores",
        json=_chore_body("Laundry", members=[bob_id]),
        headers=parent_headers,
    )

    r = client.get("/api/chores", params={"member_id": alice_id})
    assert {c["name"] for c in r.json()} == {"Dishes"}


def test_list_chores_filter_by_active(client, parent_headers):
    alice_id = _member(client, parent_headers)
    r = client.post(
        "/api/chores",
        json=_chore_body(members=[alice_id], active=False),
        headers=parent_headers,
    )
    assert r.status_code == 201

    active_only = client.get("/api/chores", params={"active": True}).json()
    assert active_only == []
    inactive_only = client.get("/api/chores", params={"active": False}).json()
    assert len(inactive_only) == 1


# ─── chore-templates feature integration (DECISIONS §13 step 5) ───────────


def _custom_suggestion(client, parent_headers, name="Source template") -> dict:
    """Create a custom template via the suggestions API and return it."""
    r = client.post(
        "/api/suggestions",
        json={
            "name": name,
            "icon": "mdi:test",
            "category": "other",
            "age_min": 6,
            "age_max": None,
            "points_suggested": 4,
            "default_recurrence_type": "daily",
            "default_recurrence_config": {},
            "description": "test source",
        },
        headers=parent_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_chore_default_save_as_suggestion_creates_template(
    client, parent_headers
):
    """save_as_suggestion defaults to True (per §6.1 dialog default).
    A new chore with a never-seen-before name produces a new template
    alongside it, and the response carries `template_created=True`."""
    r = client.post(
        "/api/chores",
        json=_chore_body("Wash car"),
        headers=parent_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["template_created"] is True
    assert body["template_id"] is not None

    suggestions = client.get(
        "/api/suggestions?source=custom", headers=parent_headers
    ).json()
    assert any(s["id"] == body["template_id"] for s in suggestions)


def test_create_chore_save_as_suggestion_false_creates_no_template(
    client, parent_headers
):
    body = _chore_body("Sweep porch")
    body["save_as_suggestion"] = False
    r = client.post("/api/chores", json=body, headers=parent_headers)
    assert r.status_code == 201
    out = r.json()
    assert out["template_created"] is False
    assert out["template_id"] is None

    customs = client.get(
        "/api/suggestions?source=custom", headers=parent_headers
    ).json()
    assert all(s["name"] != "Sweep porch" for s in customs)


def test_create_chore_save_as_suggestion_dedup_links_to_existing(
    client, parent_headers
):
    """Two chores with names that normalize the same — only the first
    creates a template. The second silently links to the existing one
    and reports `template_created=False`."""
    first = client.post(
        "/api/chores",
        json=_chore_body("Sweep porch"),
        headers=parent_headers,
    ).json()
    assert first["template_created"] is True
    template_id = first["template_id"]

    second = client.post(
        "/api/chores",
        json=_chore_body("sweep PORCH."),
        headers=parent_headers,
    ).json()
    assert second["template_created"] is False
    assert second["template_id"] == template_id


def test_create_chore_save_as_suggestion_dedups_against_starter(
    client, parent_headers
):
    """A chore named 'Make bed' (a starter library entry) does NOT
    create a duplicate custom template — it links to the starter."""
    starters = client.get(
        "/api/suggestions?source=starter", headers=parent_headers
    ).json()
    starter_make_bed = next(s for s in starters if s["name"] == "Make bed")

    r = client.post(
        "/api/chores",
        json=_chore_body("Make bed"),
        headers=parent_headers,
    ).json()
    assert r["template_created"] is False
    assert r["template_id"] == starter_make_bed["id"]


def test_create_chore_with_template_id_validates_household_scope(
    client, parent_headers
):
    """Passing a real template_id from this household is OK — chore
    records it. (Defense-in-depth: cross-household ids would be 404.)"""
    template = _custom_suggestion(client, parent_headers, name="Pre-made")
    body = _chore_body("Different chore name")
    body["template_id"] = template["id"]
    body["save_as_suggestion"] = False  # avoid auto-create on the new name

    r = client.post("/api/chores", json=body, headers=parent_headers)
    assert r.status_code == 201
    assert r.json()["template_id"] == template["id"]


def test_create_chore_with_unknown_template_id_returns_404(
    client, parent_headers
):
    body = _chore_body("Some chore")
    body["template_id"] = "00000000-0000-0000-0000-000000000000"
    r = client.post("/api/chores", json=body, headers=parent_headers)
    assert r.status_code == 404


def test_patch_chore_does_not_modify_source_template(client, parent_headers):
    """Editing a chore must not touch its source template — the chore↔
    template split is one-way."""
    template = _custom_suggestion(client, parent_headers, name="Source")
    body = _chore_body("Source", points=5)
    body["template_id"] = template["id"]
    body["save_as_suggestion"] = False

    chore_id = client.post("/api/chores", json=body, headers=parent_headers).json()[
        "id"
    ]

    # Bump the chore's points; template should be unaffected.
    client.patch(
        f"/api/chores/{chore_id}",
        json={"points": 99},
        headers=parent_headers,
    )

    template_after = client.get(
        f"/api/suggestions/{template['id']}", headers=parent_headers
    ).json()
    assert template_after["points_suggested"] == template["points_suggested"]


def test_chore_read_includes_template_id_field(client, parent_headers):
    """Existing GET / PATCH responses now carry `template_id` (default
    None for chores not spawned from a template)."""
    body = _chore_body("Plain chore")
    body["save_as_suggestion"] = False
    chore_id = client.post("/api/chores", json=body, headers=parent_headers).json()[
        "id"
    ]
    listed = client.get("/api/chores", headers=parent_headers).json()
    target = next(c for c in listed if c["id"] == chore_id)
    assert "template_id" in target
    assert target["template_id"] is None
