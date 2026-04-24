"""HABridge worker tests using FakeHAClient."""

from __future__ import annotations

from datetime import date

import pytest

from family_chores_db.models import (
    Chore,
    ChoreInstance,
    InstanceState,
    Member,
    MemberStats,
    RecurrenceType,
)
from family_chores_addon.ha.bridge import (
    SENSOR_PENDING_APPROVALS,
    HABridge,
    fc_tag,
    sensor_entity_for_member_points,
    sensor_entity_for_member_streak,
    todo_summary_for,
)
from tests._ha_fakes import FakeHAClient


async def _seed(session, *, ha_todo_entity_id="todo.alice"):
    alice = Member(
        name="Alice",
        slug="alice",
        ha_todo_entity_id=ha_todo_entity_id,
    )
    chore = Chore(name="Dishes", points=7, recurrence_type=RecurrenceType.DAILY)
    chore.assigned_members = [alice]
    stats = MemberStats(
        member_id=0,
        points_total=21,
        points_this_week=7,
        streak=3,
    )
    session.add_all([alice, chore])
    await session.flush()
    stats.member_id = alice.id
    session.add(stats)

    inst = ChoreInstance(
        chore_id=chore.id,
        member_id=alice.id,
        date=date(2026, 4, 21),
        state=InstanceState.PENDING,
    )
    session.add(inst)
    await session.flush()
    return alice, chore, inst


def _collect_set_state_calls(fake, entity_id):
    return [args for method, args in fake.calls if method == "set_state" and args[0] == entity_id]


# ─── sensor publish ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_force_flush_publishes_member_sensors(async_session_factory):
    async with async_session_factory() as s:
        alice, _, _ = await _seed(s)
        await s.commit()

    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)
    bridge.notify_member_dirty(alice.id)
    await bridge.force_flush()

    points_calls = _collect_set_state_calls(
        fake, sensor_entity_for_member_points("alice")
    )
    streak_calls = _collect_set_state_calls(
        fake, sensor_entity_for_member_streak("alice")
    )
    assert len(points_calls) == 1
    assert len(streak_calls) == 1

    _, state, attrs = points_calls[0]
    assert state == "21"  # points_total
    assert attrs["streak"] == 3
    assert attrs["points_this_week"] == 7


@pytest.mark.asyncio
async def test_force_flush_publishes_pending_approvals(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, inst = await _seed(s, ha_todo_entity_id=None)
        inst.state = InstanceState.DONE_UNAPPROVED
        await s.commit()

    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)
    bridge.notify_approvals_dirty()
    await bridge.force_flush()

    calls = _collect_set_state_calls(fake, SENSOR_PENDING_APPROVALS)
    assert len(calls) == 1
    _, state, _ = calls[0]
    assert state == "1"


@pytest.mark.asyncio
async def test_force_flush_drains_events(async_session_factory):
    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)
    bridge.enqueue_event("family_chores_completed", {"instance_id": 1, "points": 5})
    bridge.enqueue_event("family_chores_approved", {"instance_id": 2, "points": 3})
    await bridge.force_flush()

    events = [args for method, args in fake.calls if method == "fire_event"]
    assert [e[0] for e in events] == [
        "family_chores_completed",
        "family_chores_approved",
    ]


# ─── todo sync ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_instance_creates_todo_item_when_unknown(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, inst = await _seed(s)
        await s.commit()
        inst_id = inst.id

    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)
    bridge.notify_instance_changed(inst_id)
    await bridge.force_flush()

    list_state = fake.todo_lists["todo.alice"]
    assert len(list_state.items) == 1
    assert list_state.items[0]["summary"].startswith(fc_tag(inst_id))
    assert list_state.items[0]["due"] == "2026-04-21"

    # Our DB row should have the HA UID now.
    async with async_session_factory() as s:
        fresh = await s.get(ChoreInstance, inst_id)
        assert fresh.ha_todo_uid == list_state.items[0]["uid"]


@pytest.mark.asyncio
async def test_sync_instance_updates_by_uid_on_state_change(async_session_factory):
    async with async_session_factory() as s:
        alice, chore, inst = await _seed(s)
        await s.commit()
        inst_id = inst.id

    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)

    # First flush: creates item + records UID.
    bridge.notify_instance_changed(inst_id)
    await bridge.force_flush()

    # Mark instance done.
    async with async_session_factory() as s:
        inst = await s.get(ChoreInstance, inst_id)
        inst.state = InstanceState.DONE
        await s.commit()

    bridge.notify_instance_changed(inst_id)
    await bridge.force_flush()

    list_state = fake.todo_lists["todo.alice"]
    assert len(list_state.items) == 1
    assert list_state.items[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_sync_skipped_when_member_has_no_todo_entity(async_session_factory):
    async with async_session_factory() as s:
        _, _, inst = await _seed(s, ha_todo_entity_id=None)
        await s.commit()
        inst_id = inst.id

    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)
    bridge.notify_instance_changed(inst_id)
    await bridge.force_flush()

    # No todo calls — only get_items/add/update/remove would show up here.
    todo_calls = [m for m, _ in fake.calls if m.startswith("todo_")]
    assert todo_calls == []


@pytest.mark.asyncio
async def test_bridge_coalesces_duplicate_notifications(async_session_factory):
    async with async_session_factory() as s:
        alice, _, _ = await _seed(s)
        await s.commit()

    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)
    for _ in range(5):
        bridge.notify_member_dirty(alice.id)
    await bridge.force_flush()

    # Exactly one set_state per sensor, not 5.
    assert len(_collect_set_state_calls(fake, sensor_entity_for_member_points("alice"))) == 1


@pytest.mark.asyncio
async def test_event_backlog_caps_at_limit(async_session_factory):
    from family_chores_addon.ha.bridge import _EVENT_BACKLOG_LIMIT

    fake = FakeHAClient()
    bridge = HABridge(fake, async_session_factory)
    # Overfill by 5
    for i in range(_EVENT_BACKLOG_LIMIT + 5):
        bridge.enqueue_event("family_chores_completed", {"i": i})
    # Backlog holds exactly the limit, oldest were dropped
    assert len(bridge._event_backlog) == _EVENT_BACKLOG_LIMIT
    # First kept event is i=5 (first 5 were dropped)
    assert bridge._event_backlog[0][1]["i"] == 5


# ─── summary helpers ──────────────────────────────────────────────────────


def test_fc_tag_and_summary_helpers():
    assert fc_tag(42) == "[FC#42]"
    assert todo_summary_for(42, "Dishes") == "[FC#42] Dishes"
