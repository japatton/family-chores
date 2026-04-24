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

Tenant scope (step 9): `household_id: str | None` is threaded through to
every constituent service call. Add-on path passes `None`. Each daily-
rollover scheduled job in a SaaS deployment will iterate every household
and call this once per household.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_api.services.instance_service import generate_instances, mark_overdue
from family_chores_api.services.stats_service import (
    list_member_ids,
    recompute_stats_for_member,
)
from family_chores_core.streaks import crossed_milestone
from family_chores_db.models import MemberStats
from family_chores_db.scoped import scoped


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
    household_id: str | None = None,
) -> RolloverSummary:
    summary = RolloverSummary(date=today)

    summary.instances_missed = await mark_overdue(
        session, today=today, household_id=household_id
    )

    member_ids = await list_member_ids(session, household_id=household_id)
    for mid in member_ids:
        # Fetch existing MemberStats scoped to the same household, so the
        # "old streak" comparison can't accidentally read another tenant's
        # row. session.get can't take WHERE clauses; use select instead.
        old_stats_res = await session.execute(
            select(MemberStats).where(
                MemberStats.member_id == mid,
                scoped(MemberStats.household_id, household_id),
            )
        )
        old_stats = old_stats_res.scalar_one_or_none()
        old_streak = old_stats.streak if old_stats is not None else 0

        new_stats = await recompute_stats_for_member(
            session,
            mid,
            today=today,
            week_starts_on=week_starts_on,
            household_id=household_id,
        )

        milestone = crossed_milestone(old_streak, new_stats.streak)
        if milestone is not None:
            summary.milestones.append((mid, milestone))
    summary.members_updated = len(member_ids)

    summary.instances_generated = await generate_instances(
        session, today=today, household_id=household_id
    )

    return summary
