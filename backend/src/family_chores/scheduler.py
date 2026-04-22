"""APScheduler wiring.

Two jobs:
  - `midnight_rollover` — cron, 00:00 in the configured timezone. Runs the
    rollover pipeline: mark overdue, recompute stats, generate instances.
    APScheduler's `CronTrigger(timezone=…)` handles DST correctly — on
    spring-forward nights the 00:00 slot still exists; on fall-back the
    00:00 slot exists once.
  - `ha_reconcile` — interval, every 15 min. Stub until milestone 5 gives
    it real work; keeping it in place now so the scheduler config is stable.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from family_chores.core.time import local_today
from family_chores.services.rollover_service import run_rollover

log = logging.getLogger(__name__)

MIDNIGHT_JOB_ID = "midnight_rollover"
RECONCILE_JOB_ID = "ha_reconcile"
RECONCILE_INTERVAL_MIN = 15


def make_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tz: str,
    week_starts_on: str,
) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=tz)

    async def midnight_job() -> None:
        today = local_today(tz)
        async with session_factory() as session:
            try:
                summary = await run_rollover(
                    session, today=today, week_starts_on=week_starts_on
                )
                await session.commit()
                log.info(
                    "midnight rollover: date=%s missed=%d generated=%d "
                    "members=%d milestones=%d",
                    summary.date,
                    summary.instances_missed,
                    summary.instances_generated,
                    summary.members_updated,
                    len(summary.milestones),
                )
            except Exception:
                await session.rollback()
                log.exception("midnight rollover failed")

    async def reconcile_job() -> None:
        # Milestone 5 will fill this in with HA entity reconciliation.
        log.debug("ha reconcile tick (stub)")

    scheduler.add_job(
        midnight_job,
        CronTrigger(hour=0, minute=0, timezone=tz),
        id=MIDNIGHT_JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        reconcile_job,
        IntervalTrigger(minutes=RECONCILE_INTERVAL_MIN),
        id=RECONCILE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
