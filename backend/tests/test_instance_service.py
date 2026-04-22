"""Tests for instance generation and overdue marking."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from family_chores.db.models import Chore, ChoreInstance, InstanceState, Member, RecurrenceType
from family_chores.services.instance_service import generate_instances, mark_overdue


async def _seed_member(session, slug="alice"):
    m = Member(name=slug.title(), slug=slug)
    session.add(m)
    await session.flush()
    return m


async def _seed_chore(
    session, members, *, recurrence=RecurrenceType.DAILY, config=None, active=True
):
    c = Chore(
        name="Dishes",
        points=5,
        recurrence_type=recurrence,
        recurrence_config=config or {},
        active=active,
    )
    c.assigned_members = list(members)
    session.add(c)
    await session.flush()
    return c


async def _instances(session, member_id=None):
    q = select(ChoreInstance)
    if member_id is not None:
        q = q.where(ChoreInstance.member_id == member_id)
    return list((await session.execute(q)).scalars().all())


# ─── generate_instances ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_creates_one_row_per_member_per_due_date(async_session):
    alice = await _seed_member(async_session, "alice")
    bob = await _seed_member(async_session, "bob")
    await _seed_chore(async_session, [alice, bob], recurrence=RecurrenceType.DAILY)
    await async_session.commit()

    today = date(2026, 4, 21)
    count = await generate_instances(async_session, today=today, horizon_days=2)
    # 2 members x3 dates (today + 2) = 6
    assert count == 6

    insts = await _instances(async_session)
    assert len(insts) == 6
    assert {(i.member_id, i.date) for i in insts} == {
        (alice.id, today),
        (alice.id, today + timedelta(days=1)),
        (alice.id, today + timedelta(days=2)),
        (bob.id, today),
        (bob.id, today + timedelta(days=1)),
        (bob.id, today + timedelta(days=2)),
    }
    assert all(i.state is InstanceState.PENDING for i in insts)


@pytest.mark.asyncio
async def test_generate_is_idempotent(async_session):
    alice = await _seed_member(async_session)
    await _seed_chore(async_session, [alice])
    await async_session.commit()

    today = date(2026, 4, 21)
    first = await generate_instances(async_session, today=today, horizon_days=2)
    second = await generate_instances(async_session, today=today, horizon_days=2)
    assert first == 3
    assert second == 0
    assert len(await _instances(async_session)) == 3


@pytest.mark.asyncio
async def test_generate_preserves_existing_instance_state(async_session):
    alice = await _seed_member(async_session)
    chore = await _seed_chore(async_session, [alice])
    await async_session.commit()

    today = date(2026, 4, 21)
    # Pre-insert a DONE instance
    async_session.add(
        ChoreInstance(
            chore_id=chore.id,
            member_id=alice.id,
            date=today,
            state=InstanceState.DONE,
            points_awarded=5,
        )
    )
    await async_session.commit()

    await generate_instances(async_session, today=today, horizon_days=2)
    await async_session.commit()

    insts = await _instances(async_session)
    today_inst = next(i for i in insts if i.date == today)
    assert today_inst.state is InstanceState.DONE
    assert today_inst.points_awarded == 5


@pytest.mark.asyncio
async def test_generate_skips_inactive_chore(async_session):
    alice = await _seed_member(async_session)
    await _seed_chore(async_session, [alice], active=False)
    await async_session.commit()

    count = await generate_instances(async_session, today=date(2026, 4, 21), horizon_days=2)
    assert count == 0
    assert await _instances(async_session) == []


@pytest.mark.asyncio
async def test_generate_weekdays_only(async_session):
    alice = await _seed_member(async_session)
    await _seed_chore(async_session, [alice], recurrence=RecurrenceType.WEEKDAYS)
    await async_session.commit()

    # 2026-04-20 Mon → 2026-04-26 Sun ⇒ 5 weekdays
    count = await generate_instances(
        async_session, today=date(2026, 4, 20), horizon_days=6
    )
    assert count == 5


@pytest.mark.asyncio
async def test_generate_unassigned_chore_produces_nothing(async_session):
    await _seed_chore(async_session, [])  # no assigned members
    await async_session.commit()
    count = await generate_instances(async_session, today=date(2026, 4, 21), horizon_days=2)
    assert count == 0


# ─── mark_overdue ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_overdue_updates_pending_and_done_unapproved(async_session):
    alice = await _seed_member(async_session)
    chore = await _seed_chore(async_session, [alice])
    await async_session.commit()

    yesterday = date(2026, 4, 20)
    today = date(2026, 4, 21)
    async_session.add_all(
        [
            ChoreInstance(chore_id=chore.id, member_id=alice.id, date=yesterday,
                          state=InstanceState.PENDING),
            ChoreInstance(chore_id=chore.id, member_id=alice.id,
                          date=yesterday - timedelta(days=1),
                          state=InstanceState.DONE_UNAPPROVED),
            # Already done — should NOT change
            ChoreInstance(chore_id=chore.id, member_id=alice.id,
                          date=yesterday - timedelta(days=2),
                          state=InstanceState.DONE, points_awarded=5),
            # Today — should NOT change
            ChoreInstance(chore_id=chore.id, member_id=alice.id, date=today,
                          state=InstanceState.PENDING),
        ]
    )
    await async_session.commit()

    updated = await mark_overdue(async_session, today=today)
    assert updated == 2

    insts = {i.date: i.state for i in await _instances(async_session)}
    assert insts[yesterday] is InstanceState.MISSED
    assert insts[yesterday - timedelta(days=1)] is InstanceState.MISSED
    assert insts[yesterday - timedelta(days=2)] is InstanceState.DONE
    assert insts[today] is InstanceState.PENDING


@pytest.mark.asyncio
async def test_mark_overdue_noop_when_nothing_pending(async_session):
    alice = await _seed_member(async_session)
    chore = await _seed_chore(async_session, [alice])
    await async_session.commit()

    today = date(2026, 4, 21)
    async_session.add(
        ChoreInstance(
            chore_id=chore.id,
            member_id=alice.id,
            date=today - timedelta(days=1),
            state=InstanceState.DONE,
            points_awarded=5,
        )
    )
    await async_session.commit()

    assert await mark_overdue(async_session, today=today) == 0
