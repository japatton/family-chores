"""Reconciler tests — verify HA todo state converges with SQLite state."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from family_chores_db.models import (
    Chore,
    ChoreInstance,
    InstanceState,
    Member,
    RecurrenceType,
)

from family_chores_addon.ha.reconcile import reconcile_once
from tests._ha_fakes import FakeHAClient


async def _seed_member_with_instances(
    session, *, count: int, entity_id: str = "todo.alice", start: date = date(2026, 4, 21)
):
    alice = Member(name="Alice", slug="alice", ha_todo_entity_id=entity_id)
    chore = Chore(name="Dishes", points=5, recurrence_type=RecurrenceType.DAILY)
    chore.assigned_members = [alice]
    session.add_all([alice, chore])
    await session.flush()
    instances = []
    for i in range(count):
        inst = ChoreInstance(
            chore_id=chore.id,
            member_id=alice.id,
            date=start + timedelta(days=i),
            state=InstanceState.PENDING,
        )
        session.add(inst)
        instances.append(inst)
    await session.flush()
    return alice, chore, instances


@pytest.mark.asyncio
async def test_reconcile_creates_missing_items(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, insts = await _seed_member_with_instances(s, count=3)
        await s.commit()
        inst_ids = [i.id for i in insts]

    fake = FakeHAClient()
    fake.ensure_list("todo.alice")  # empty on HA side

    result = await reconcile_once(fake, async_session_factory, today=date(2026, 4, 21))
    assert result.items_created == 3
    assert result.items_deleted == 0
    assert result.items_updated == 0
    assert result.members_processed == 1

    # Our DB now has ha_todo_uid populated for each instance.
    async with async_session_factory() as s:
        for iid in inst_ids:
            inst = await s.get(ChoreInstance, iid)
            assert inst.ha_todo_uid is not None


@pytest.mark.asyncio
async def test_reconcile_deletes_orphan_items(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, [inst] = await _seed_member_with_instances(s, count=1)
        await s.commit()

    fake = FakeHAClient()
    fake.ensure_list("todo.alice")
    # One of ours (valid) and one orphan (fake FC id)
    fake.todo_lists["todo.alice"].items = [
        {
            "uid": "uid-current",
            "summary": f"[FC#{inst.id}] Dishes",
            "status": "needs_action",
            "due": "2026-04-21",
        },
        {
            "uid": "uid-orphan",
            "summary": "[FC#9999] Ghost Chore",
            "status": "needs_action",
            "due": "2026-04-20",
        },
        # A non-FC item — should be left alone.
        {
            "uid": "uid-shopping",
            "summary": "Milk",
            "status": "needs_action",
            "due": None,
        },
    ]

    result = await reconcile_once(fake, async_session_factory, today=date(2026, 4, 21))

    assert result.items_deleted == 1
    assert result.items_created == 0
    remaining = {it["uid"] for it in fake.todo_lists["todo.alice"].items}
    assert "uid-orphan" not in remaining
    assert "uid-shopping" in remaining
    assert "uid-current" in remaining


@pytest.mark.asyncio
async def test_reconcile_updates_drifted_item(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, [inst] = await _seed_member_with_instances(s, count=1)
        # Mark done in DB but HA shows needs_action.
        inst.state = InstanceState.DONE
        await s.commit()
        inst_id = inst.id

    fake = FakeHAClient()
    fake.ensure_list("todo.alice")
    fake.todo_lists["todo.alice"].items = [
        {
            "uid": "uid-current",
            "summary": f"[FC#{inst_id}] Dishes",
            "status": "needs_action",  # drift: DB says DONE → completed
            "due": "2026-04-21",
        }
    ]

    result = await reconcile_once(fake, async_session_factory, today=date(2026, 4, 21))
    assert result.items_updated == 1
    assert fake.todo_lists["todo.alice"].items[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_reconcile_records_uid_from_existing_match(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, [inst] = await _seed_member_with_instances(s, count=1)
        await s.commit()
        inst_id = inst.id

    fake = FakeHAClient()
    fake.ensure_list("todo.alice")
    fake.todo_lists["todo.alice"].items = [
        {
            "uid": "ha-uid-123",
            "summary": f"[FC#{inst_id}] Dishes",
            "status": "needs_action",
            "due": "2026-04-21",
        }
    ]

    await reconcile_once(fake, async_session_factory, today=date(2026, 4, 21))

    async with async_session_factory() as s:
        inst = await s.get(ChoreInstance, inst_id)
        assert inst.ha_todo_uid == "ha-uid-123"


@pytest.mark.asyncio
async def test_reconcile_skips_members_without_entity(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, [inst] = await _seed_member_with_instances(s, count=1, entity_id=None)
        await s.commit()

    fake = FakeHAClient()
    result = await reconcile_once(fake, async_session_factory, today=date(2026, 4, 21))
    assert result.members_processed == 0
    # No HA calls at all.
    assert fake.calls == []


@pytest.mark.asyncio
async def test_reconcile_continues_through_per_member_errors(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, insts = await _seed_member_with_instances(s, count=1, entity_id="todo.alice")
        # Add a second member
        bob = Member(name="Bob", slug="bob", ha_todo_entity_id="todo.bob")
        s.add(bob)
        await s.flush()
        chore.assigned_members.append(bob)
        bob_inst = ChoreInstance(
            chore_id=chore.id, member_id=bob.id, date=date(2026, 4, 21)
        )
        s.add(bob_inst)
        await s.commit()

    fake = FakeHAClient()
    # Make the first call to todo_get_items fail.
    from family_chores_addon.ha.client import HAUnavailableError
    fake.fail_next["todo_get_items"] = HAUnavailableError("alice is down")

    result = await reconcile_once(fake, async_session_factory, today=date(2026, 4, 21))
    # Both members were attempted; only alice errored.
    assert result.members_processed == 2
    assert len(result.errors) == 1
