"""Member-stats recomputation.

Stats are a cache — everything in `member_stats` is derivable from
`chore_instances`. We recompute the whole thing at each rollover rather than
maintaining incremental invariants, because the dataset is tiny (family
scale) and correctness is trivially obvious this way.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores.core.points import week_anchor_for
from family_chores.core.streaks import compute_streak
from family_chores.db.models import ChoreInstance, InstanceState, Member, MemberStats


async def recompute_stats_for_member(
    session: AsyncSession,
    member_id: int,
    *,
    today: date,
    week_starts_on: str,
    streak_lookback_days: int = 365,
) -> MemberStats:
    stats = await session.get(MemberStats, member_id)
    if stats is None:
        stats = MemberStats(member_id=member_id)
        session.add(stats)

    total_res = await session.execute(
        select(ChoreInstance.points_awarded).where(ChoreInstance.member_id == member_id)
    )
    stats.points_total = sum(total_res.scalars().all())

    this_anchor = week_anchor_for(today, week_starts_on)
    week_res = await session.execute(
        select(ChoreInstance.points_awarded)
        .where(ChoreInstance.member_id == member_id)
        .where(ChoreInstance.date >= this_anchor)
        .where(ChoreInstance.date <= today)
    )
    stats.points_this_week = sum(week_res.scalars().all())
    stats.week_anchor = this_anchor

    # Streak is computed as of the end of yesterday — the last day whose
    # state is finalised after mark_overdue runs at midnight. Counting
    # `today` would make the streak drop to zero the instant we generate
    # today's PENDING instances, which is user-hostile and contradicts the
    # "ended in done" semantic in the prompt.
    streak_as_of = today - timedelta(days=1)
    window_start = streak_as_of - timedelta(days=streak_lookback_days)
    states_res = await session.execute(
        select(ChoreInstance.date, ChoreInstance.state)
        .where(ChoreInstance.member_id == member_id)
        .where(ChoreInstance.date <= streak_as_of)
        .where(ChoreInstance.date >= window_start)
    )
    states_by_date: dict[date, list[InstanceState]] = {}
    for d, s in states_res.all():
        states_by_date.setdefault(d, []).append(s)
    stats.streak = compute_streak(states_by_date, streak_as_of)

    last_all_done: date | None = None
    for d in sorted(states_by_date.keys(), reverse=True):
        states = states_by_date[d]
        if states and all(s is InstanceState.DONE for s in states):
            last_all_done = d
            break
    stats.last_all_done_date = last_all_done

    await session.flush()
    return stats


async def list_member_ids(session: AsyncSession) -> list[int]:
    res = await session.execute(select(Member.id))
    return list(res.scalars().all())
