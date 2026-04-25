"""Defensive: chore_template rows must be invisible to HA sync.

Pinned per DECISIONS §13 §7 ("HA sync defensive test"). The rationale:
templates are reusable blueprints, not active state — they have no
schedule, no assignment, no completion. They must never be mirrored
into HA todo entities, sensors, or events.

The bridge and reconciler iterate `Member` and `ChoreInstance` rows
only. They never SELECT from `chore_template`, so this test really
just pins that contract — a future "promote a template to a sensor"
refactor would have to delete this test, which forces a discussion.

Companion API tests for the suggestions endpoints live in
`test_api_suggestions.py`; companion seeder tests in `test_seeding.py`.
"""

from __future__ import annotations

from datetime import date

import pytest
from family_chores_api.services.starter_seeding import seed_starter_library
from family_chores_db.models import ChoreInstance, ChoreTemplate, Member
from sqlalchemy import select

from family_chores_addon.ha.reconcile import reconcile_once
from tests._ha_fakes import FakeHAClient


@pytest.mark.asyncio
async def test_seeded_templates_do_not_create_chore_instances(async_session):
    """A bare-DB seed produces 46 templates and zero chore_instances.
    Without chores or instances, there is nothing for the HA bridge or
    the reconciler to mirror."""
    await seed_starter_library(async_session, household_id=None)
    await async_session.commit()

    template_count = (
        await async_session.execute(select(ChoreTemplate))
    ).scalars().all()
    assert len(template_count) == 46

    instances = (
        await async_session.execute(select(ChoreInstance))
    ).scalars().all()
    assert instances == [], "templates must not generate chore_instances"


@pytest.mark.asyncio
async def test_reconcile_after_seeding_creates_zero_todo_items(
    async_session, async_session_factory
):
    """End-to-end: a freshly-seeded household with a Local-Todo-mapped
    member, no chores, no instances. `reconcile_once` should look at
    the empty instance set and push zero items into the FakeHAClient."""
    member = Member(
        name="Alice",
        slug="alice",
        ha_todo_entity_id="todo.alice",
    )
    async_session.add(member)
    await async_session.flush()

    await seed_starter_library(async_session, household_id=None)
    await async_session.commit()

    fake = FakeHAClient()
    fake.ensure_list("todo.alice")
    result = await reconcile_once(
        fake, async_session_factory, today=date(2026, 4, 25)
    )

    assert result.members_processed == 1
    assert result.items_created == 0, (
        "templates must not produce HA todo items via the reconciler"
    )
    assert result.items_updated == 0
    assert result.items_deleted == 0
    assert fake.todo_lists["todo.alice"].items == []


@pytest.mark.asyncio
async def test_reconcile_does_not_query_chore_template_table(
    async_session, async_session_factory, monkeypatch
):
    """Structural pin: spy on session.execute and verify that none of the
    SQL the reconciler emits references the chore_template table.

    A future change that adds a SELECT FROM chore_template inside the
    reconciler (intentionally or not) would fail this test and force
    a deliberate decision.
    """
    member = Member(
        name="Bob", slug="bob", ha_todo_entity_id="todo.bob"
    )
    async_session.add(member)
    await seed_starter_library(async_session, household_id=None)
    await async_session.commit()

    queries: list[str] = []
    # Use a SQLAlchemy event listener on the underlying sync engine —
    # cleaner than monkey-patching session.execute, and captures every
    # statement the reconciler emits regardless of which session
    # instance it opens.
    from sqlalchemy import event

    engine = async_session.bind
    sync_engine = engine.sync_engine  # type: ignore[union-attr]

    def _capture(_conn, _cursor, statement, *_args, **_kw):
        queries.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _capture)
    try:
        fake = FakeHAClient()
        fake.ensure_list("todo.bob")
        await reconcile_once(
            fake, async_session_factory, today=date(2026, 4, 25)
        )
    finally:
        event.remove(sync_engine, "before_cursor_execute", _capture)

    joined = "\n".join(queries).lower()
    assert "chore_template" not in joined, (
        "reconciler queried chore_template — templates are not HA state"
    )
    assert "household_starter_suppression" not in joined, (
        "reconciler queried suppression table — that's a parent-mode concern"
    )
    # Sanity: it DID query the tables it's supposed to.
    assert "members" in joined or "member" in joined
