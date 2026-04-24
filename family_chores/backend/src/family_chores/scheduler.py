"""APScheduler wiring.

Two jobs:
  - `midnight_rollover` — cron, 00:00 in the configured timezone. Runs the
    rollover pipeline (mark overdue, recompute stats, generate instances)
    and enqueues streak-milestone events into the HA bridge.
  - `ha_reconcile` — interval, every 15 min. Drives
    `family_chores.ha.reconcile.reconcile_once` so HA todo state converges
    with SQLite even when individual bridge calls dropped.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from family_chores_core.time import local_today
from family_chores_api.bridge import BridgeProtocol
from family_chores.ha.client import HAClient
from family_chores.ha.reconcile import reconcile_once
from family_chores_api.services.rollover_service import run_rollover

log = logging.getLogger(__name__)

MIDNIGHT_JOB_ID = "midnight_rollover"
RECONCILE_JOB_ID = "ha_reconcile"
RECONCILE_INTERVAL_MIN = 15

_EVENT_STREAK_MILESTONE = "family_chores_streak_milestone"


def make_scheduler(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tz: str,
    week_starts_on: str,
    bridge: BridgeProtocol | None = None,
    ha_client: HAClient | None = None,
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
                if bridge is not None:
                    for member_id, streak_days in summary.milestones:
                        bridge.enqueue_event(
                            _EVENT_STREAK_MILESTONE,
                            {"member_id": member_id, "streak_days": streak_days},
                        )
                        bridge.notify_member_dirty(member_id)
            except Exception:
                await session.rollback()
                log.exception("midnight rollover failed")

    async def reconcile_job() -> None:
        if ha_client is None or bridge is None:
            log.debug("ha reconcile: no HA client, skipping")
            return
        today = local_today(tz)
        try:
            result = await reconcile_once(ha_client, session_factory, today=today)
            log.info(
                "ha reconcile: members=%d created=%d updated=%d deleted=%d errors=%d",
                result.members_processed,
                result.items_created,
                result.items_updated,
                result.items_deleted,
                len(result.errors),
            )
        except Exception:
            log.exception("ha reconcile failed")

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
