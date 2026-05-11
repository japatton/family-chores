"""Timezone-aware regression tests for the weekly-cap counter.

Pins **D-2** from the v0.5.0 ultra-review:
`_count_redemptions_this_week` used to compose `week_start` as a
naive datetime from `week_anchor` (a *local* date) and compare it
directly against `Redemption.requested_at` (naive UTC). For
non-UTC families the comparison drifted by the local-to-UTC offset
(up to 7h in PDT, 14h in NZ).

The test below seeds a redemption at a fixed UTC datetime and
exercises the cap counter from two different timezones to prove
that the same UTC instant lands in different weeks depending on
the user's local tz — which is exactly the bug the fix addresses.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from family_chores_api.services.redemption_service import (
    _count_redemptions_this_week,
)
from family_chores_db.models import (
    Member,
    Redemption,
    RedemptionState,
    Reward,
)


@pytest.mark.asyncio
async def test_count_redemptions_respects_tz_boundary(async_session_factory):
    """A redemption at 2026-05-04 06:00 UTC sits in different weeks
    depending on the user's tz:

      - UTC:                  Monday 2026-05-04 06:00 → THIS week
      - America/Los_Angeles:  Sunday 2026-05-03 23:00 → LAST week (PDT, UTC-7)

    Pre-fix, the count used naive comparison and always reported "this
    week" because `naive(2026-05-04 06:00) >= naive(2026-05-04 00:00)`
    held regardless of tz. Post-fix, week_start is converted local→UTC
    before compare, so the LA query correctly attributes the seed to
    last week.
    """
    async with async_session_factory() as session:
        member = Member(name="Alice", slug="alice", color="#f00")
        session.add(member)
        await session.flush()
        reward = Reward(
            id="r1",
            name="Test",
            cost_points=10,
            household_id=None,
            active=True,
            max_per_week=1,
        )
        session.add(reward)
        await session.flush()
        # Pin requested_at at 2026-05-04 06:00 UTC. Monday in UTC; in
        # PT (UTC-7) it's still Sunday 23:00 — pre-Monday-midnight-PT.
        session.add(
            Redemption(
                id="seed",
                member_id=member.id,
                reward_id=reward.id,
                household_id=None,
                state=RedemptionState.PENDING_APPROVAL,
                cost_points_at_redeem=10,
                reward_name_at_redeem="Test",
                actor_requested="seed",
                requested_at=datetime(2026, 5, 4, 6, 0),  # naive UTC
            )
        )
        await session.commit()

        # Week anchor in UTC for Monday 2026-05-04.
        utc_anchor = date(2026, 5, 4)

        # Query from UTC's perspective — the seed should count.
        count_utc = await _count_redemptions_this_week(
            session,
            reward_id="r1",
            member_id=member.id,
            week_anchor=utc_anchor,
            tz="UTC",
            household_id=None,
        )
        assert count_utc == 1, (
            "UTC: seed at 06:00 Mon is this week (week_start=00:00) → should count"
        )

        # Query from LA's perspective — same week anchor Monday, but
        # week_start translates to 07:00 UTC (PDT, UTC-7). Seed at
        # 06:00 UTC is BEFORE the local Monday-midnight, so it's last
        # week.
        count_la = await _count_redemptions_this_week(
            session,
            reward_id="r1",
            member_id=member.id,
            week_anchor=utc_anchor,
            tz="America/Los_Angeles",
            household_id=None,
        )
        assert count_la == 0, (
            "LA: seed at 06:00 UTC = Sunday 23:00 PT = LAST week → should not count"
        )


@pytest.mark.asyncio
async def test_count_redemptions_unambiguous_midweek(async_session_factory):
    """Sanity: a Wednesday-afternoon redemption is unambiguously
    this week regardless of tz. Tests that the conversion doesn't
    break the common case."""
    async with async_session_factory() as session:
        member = Member(name="Bob", slug="bob", color="#0f0")
        session.add(member)
        await session.flush()
        reward = Reward(
            id="r1",
            name="Test",
            cost_points=10,
            household_id=None,
            active=True,
            max_per_week=1,
        )
        session.add(reward)
        await session.flush()
        # Wednesday 2026-05-06 14:00 UTC — afternoon, clearly mid-week
        # in any tz.
        session.add(
            Redemption(
                id="seed",
                member_id=member.id,
                reward_id=reward.id,
                household_id=None,
                state=RedemptionState.PENDING_APPROVAL,
                cost_points_at_redeem=10,
                reward_name_at_redeem="Test",
                actor_requested="seed",
                requested_at=datetime(2026, 5, 6, 14, 0),
            )
        )
        await session.commit()

        for tz in ("UTC", "America/Los_Angeles", "Pacific/Auckland"):
            count = await _count_redemptions_this_week(
                session,
                reward_id="r1",
                member_id=member.id,
                week_anchor=date(2026, 5, 4),
                tz=tz,
                household_id=None,
            )
            assert count == 1, f"{tz}: mid-week redemption should always count"
