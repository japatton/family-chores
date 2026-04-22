"""Smoke tests for the scheduler factory.

We don't start the scheduler here — that's time-sensitive and unreliable
to test cleanly. Instead we verify the registered jobs look right (trigger
type, id, coalesce), and that the midnight job callable is invocable in
isolation against a real session. End-to-end scheduler run is covered by
the lifespan boot test over in test_lifespan_integration.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from family_chores.db.models import Chore, ChoreInstance, Member, MemberStats, RecurrenceType
from family_chores.scheduler import (
    MIDNIGHT_JOB_ID,
    RECONCILE_INTERVAL_MIN,
    RECONCILE_JOB_ID,
    make_scheduler,
)
from family_chores.services.rollover_service import run_rollover


def test_scheduler_registers_both_jobs(async_session_factory):
    scheduler = make_scheduler(async_session_factory, tz="UTC", week_starts_on="monday")
    try:
        jobs = {job.id: job for job in scheduler.get_jobs()}
        assert set(jobs.keys()) == {MIDNIGHT_JOB_ID, RECONCILE_JOB_ID}
        assert isinstance(jobs[MIDNIGHT_JOB_ID].trigger, CronTrigger)
        assert isinstance(jobs[RECONCILE_JOB_ID].trigger, IntervalTrigger)
        # Midnight job: coalesce=True, max_instances=1, misfire_grace_time>=1h
        midnight = jobs[MIDNIGHT_JOB_ID]
        assert midnight.coalesce is True
        assert midnight.max_instances == 1
        assert midnight.misfire_grace_time is not None
        assert midnight.misfire_grace_time >= 3600
        # Reconcile: 15 minute interval
        reconcile = jobs[RECONCILE_JOB_ID]
        assert reconcile.trigger.interval.total_seconds() == RECONCILE_INTERVAL_MIN * 60
    finally:
        # We never called start(), so nothing to shut down cleanly — but be
        # explicit in case APScheduler grew eager behaviour.
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_scheduler_accepts_named_timezone(async_session_factory):
    # Does not raise for a real IANA zone.
    scheduler = make_scheduler(
        async_session_factory, tz="America/Los_Angeles", week_starts_on="sunday"
    )
    if scheduler.running:
        scheduler.shutdown(wait=False)


@pytest.mark.asyncio
async def test_rollover_through_session_factory(async_session_factory):
    """The scheduler's midnight job will hold its session briefly. Exercise
    that pattern here to catch lifetime bugs without relying on the scheduler.
    """
    # Seed some data via a short-lived session.
    async with async_session_factory() as session:
        alice = Member(name="Alice", slug="alice")
        chore = Chore(name="Dishes", points=5, recurrence_type=RecurrenceType.DAILY)
        chore.assigned_members = [alice]
        session.add_all([alice, chore])
        await session.commit()
        alice_id = alice.id

    # A second, scheduler-style session: open fresh, run rollover, commit.
    async with async_session_factory() as session:
        summary = await run_rollover(
            session, today=date(2026, 4, 21), week_starts_on="monday"
        )
        await session.commit()
        assert summary.members_updated == 1
        # At least today + 14 instances should have been generated.
        from sqlalchemy import select
        res = await session.execute(select(ChoreInstance))
        assert len(res.scalars().all()) >= 15

    # MemberStats should have been persisted.
    async with async_session_factory() as session:
        stats = await session.get(MemberStats, alice_id)
        assert stats is not None
        assert stats.streak == 0  # no done days
        assert stats.points_total == 0
