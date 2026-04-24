"""Daily rollover — the single orchestrated unit of work fired at midnight.

Same function is used at app startup as a catch-up: if the app was down at
midnight, running this on boot produces the same end state. All constituent
operations are idempotent.

Steps:
  1. `mark_overdue` — yesterday's unresolved `pending`/`done_unapproved`
     instances become `missed`.
  2. Per-member stats recomputation (points total, points this week with
     week-anchor reset, streak). Streak-milestone transitions are detected
     here and returned in the summary for the HA bridge (milestone 5) to
     turn into events.
  3. `generate_instances` — materialise the next 14 days. Must come after
     step 1, otherwise overdue ones would be regenerated for the past.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_core.streaks import crossed_milestone
from family_chores.db.models import MemberStats
from family_chores.services.instance_service import generate_instances, mark_overdue
from family_chores.services.stats_service import list_member_ids, recompute_stats_for_member


@dataclass(slots=True)
class RolloverSummary:
    date: date_type
    instances_missed: int = 0
    instances_generated: int = 0
    members_updated: int = 0
    milestones: list[tuple[int, int]] = field(default_factory=list)


async def run_rollover(
    session: AsyncSession,
    *,
    today: date_type,
    week_starts_on: str,
) -> RolloverSummary:
    summary = RolloverSummary(date=today)

    summary.instances_missed = await mark_overdue(session, today=today)

    member_ids = await list_member_ids(session)
    for mid in member_ids:
        old_stats = await session.get(MemberStats, mid)
        old_streak = old_stats.streak if old_stats is not None else 0

        new_stats = await recompute_stats_for_member(
            session, mid, today=today, week_starts_on=week_starts_on
        )

        milestone = crossed_milestone(old_streak, new_stats.streak)
        if milestone is not None:
            summary.milestones.append((mid, milestone))
    summary.members_updated = len(member_ids)

    summary.instances_generated = await generate_instances(session, today=today)

    return summary
