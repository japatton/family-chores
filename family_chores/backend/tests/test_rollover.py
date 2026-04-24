"""End-to-end rollover tests over a seeded async DB."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from family_chores_core.streaks import STREAK_MILESTONES
from family_chores_db.models import (
    Chore,
    ChoreInstance,
    InstanceState,
    Member,
    MemberStats,
    RecurrenceType,
)
from family_chores_api.services.rollover_service import run_rollover


async def _seed_member(session, slug="alice", requires_approval=False):
    m = Member(name=slug.title(), slug=slug, requires_approval=requires_approval)
    session.add(m)
    await session.flush()
    return m


async def _seed_chore(session, members, *, points=5, recurrence=RecurrenceType.DAILY):
    c = Chore(
        name="Dishes",
        points=points,
        recurrence_type=recurrence,
        recurrence_config={},
    )
    c.assigned_members = list(members)
    session.add(c)
    await session.flush()
    return c


async def _seed_run_of_done_days(session, member, chore, *, end_date, count, points=5):
    for i in range(count):
        d = end_date - timedelta(days=i)
        session.add(
            ChoreInstance(
                chore_id=chore.id,
                member_id=member.id,
                date=d,
                state=InstanceState.DONE,
                points_awarded=points,
            )
        )


@pytest.mark.asyncio
async def test_rollover_marks_overdue_and_generates(async_session):
    alice = await _seed_member(async_session)
    chore = await _seed_chore(async_session, [alice])
    await async_session.commit()

    today = date(2026, 4, 21)
    # A pending instance from yesterday and one from today.
    async_session.add_all(
        [
            ChoreInstance(
                chore_id=chore.id, member_id=alice.id, date=today - timedelta(days=1)
            ),
            ChoreInstance(chore_id=chore.id, member_id=alice.id, date=today),
        ]
    )
    await async_session.commit()

    summary = await run_rollover(async_session, today=today, week_starts_on="monday")
    await async_session.commit()

    assert summary.instances_missed == 1
    # Should generate future instances (today already exists so at least 14).
    assert summary.instances_generated >= 14
    assert summary.members_updated == 1


@pytest.mark.asyncio
async def test_rollover_recomputes_points_and_streak(async_session):
    alice = await _seed_member(async_session)
    chore = await _seed_chore(async_session, [alice])
    await async_session.commit()

    today = date(2026, 4, 21)  # a Tuesday
    # 4 consecutive all-done days ending yesterday (Mon, Sun, Sat, Fri).
    await _seed_run_of_done_days(
        async_session, alice, chore, end_date=today - timedelta(days=1), count=4
    )
    await async_session.commit()

    summary = await run_rollover(async_session, today=today, week_starts_on="monday")
    await async_session.commit()

    stats = await async_session.get(MemberStats, alice.id)
    assert stats is not None
    # 4 done days x5 points = 20 lifetime
    assert stats.points_total == 20
    # This week (Mon 2026-04-20) has 1 all-done day x5 pts.
    assert stats.week_anchor == date(2026, 4, 20)
    assert stats.points_this_week == 5
    assert stats.streak == 4
    assert stats.last_all_done_date == today - timedelta(days=1)

    assert summary.milestones == [(alice.id, 3)]


@pytest.mark.asyncio
async def test_rollover_fires_each_milestone_exactly_once(async_session):
    alice = await _seed_member(async_session)
    chore = await _seed_chore(async_session, [alice])
    await async_session.commit()

    today = date(2026, 4, 21)

    # Start with no done days → first rollover sets streak to 0.
    await run_rollover(async_session, today=today, week_starts_on="monday")
    await async_session.commit()
    stats = await async_session.get(MemberStats, alice.id)
    assert stats.streak == 0

    # Seed 3 consecutive done days ending yesterday, rerun rollover.
    await _seed_run_of_done_days(
        async_session, alice, chore, end_date=today - timedelta(days=1), count=3
    )
    await async_session.commit()
    summary = await run_rollover(async_session, today=today, week_starts_on="monday")
    await async_session.commit()
    assert (alice.id, 3) in summary.milestones

    # Running rollover again on the same day: streak unchanged, no new milestone.
    summary2 = await run_rollover(async_session, today=today, week_starts_on="monday")
    await async_session.commit()
    assert summary2.milestones == []


@pytest.mark.asyncio
async def test_rollover_week_reset_is_idempotent(async_session):
    alice = await _seed_member(async_session)
    chore = await _seed_chore(async_session, [alice])
    await async_session.commit()

    # Stash some points in week A.
    async_session.add(
        ChoreInstance(
            chore_id=chore.id,
            member_id=alice.id,
            date=date(2026, 4, 13),  # Mon of week A
            state=InstanceState.DONE,
            points_awarded=10,
        )
    )
    await async_session.commit()

    # Rollover on a date inside week A.
    await run_rollover(async_session, today=date(2026, 4, 15), week_starts_on="monday")
    await async_session.commit()
    stats = await async_session.get(MemberStats, alice.id)
    assert stats.week_anchor == date(2026, 4, 13)
    assert stats.points_this_week == 10

    # Rollover on a date inside week B — week_anchor advances, points_this_week resets.
    await run_rollover(async_session, today=date(2026, 4, 21), week_starts_on="monday")
    await async_session.commit()
    stats = await async_session.get(MemberStats, alice.id)
    assert stats.week_anchor == date(2026, 4, 20)
    assert stats.points_this_week == 0  # no done-days in the new week yet


@pytest.mark.asyncio
async def test_rollover_handles_zero_member_db(async_session):
    summary = await run_rollover(
        async_session, today=date(2026, 4, 21), week_starts_on="monday"
    )
    await async_session.commit()
    assert summary.members_updated == 0
    assert summary.instances_missed == 0
    assert summary.instances_generated == 0
    assert summary.milestones == []


def test_streak_milestones_constant_exposed_through_service():
    # Import-level smoke test: downstream code (HA bridge) will import this.
    assert STREAK_MILESTONES[0] == 3
