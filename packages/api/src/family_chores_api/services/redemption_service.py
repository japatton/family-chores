"""Redemption state machine + point integration.

Owns the three transitions for a `Redemption` row:

  - `request_redemption(member, reward)` → creates a row in
    `pending_approval` after deducting the cost from the member's
    `MemberStats`. Insufficient balance raises `InvalidStateError`;
    weekly cap (when reward.max_per_week is set) raises the same.

  - `approve_redemption(redemption)` → flips state to `approved`,
    records who/when. No point change — the deduction was at request
    time.

  - `deny_redemption(redemption, reason)` → flips state to `denied`,
    records who/when/why, refunds the cost via `bonus_points_total +=
    cost`. The signed-bonus path from F-S001 is what makes the refund
    work without a separate "reserved points" mechanism.

Each function mutates the DB and writes an `ActivityLog` row. The
caller (router) owns the commit boundary, the WS/HA event firing,
and the outward `RedemptionRead` mapping.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_api.errors import (
    ConflictError,
    InvalidStateError,
    NotFoundError,
)
from family_chores_core.points import week_anchor_for
from family_chores_core.time import utcnow
from family_chores_db.models import (
    ActivityLog,
    Member,
    MemberStats,
    Redemption,
    RedemptionState,
    Reward,
)
from family_chores_db.scoped import scoped


def _log(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    payload: dict[str, Any],
    household_id: str | None,
) -> None:
    session.add(
        ActivityLog(
            actor=actor,
            action=action,
            payload=payload,
            household_id=household_id,
        )
    )


async def _load_reward_active(
    session: AsyncSession, reward_id: str, household_id: str | None
) -> Reward:
    res = await session.execute(
        select(Reward).where(
            Reward.id == reward_id,
            scoped(Reward.household_id, household_id),
        )
    )
    reward = res.scalar_one_or_none()
    if reward is None:
        raise NotFoundError(f"reward {reward_id!r} not found")
    if not reward.active:
        # Soft-deleted rewards are read-only — kid can't redeem against
        # them. Parent can read for history but the catalogue list filters
        # active=True by default.
        raise ConflictError(f"reward {reward_id!r} is no longer available")
    return reward


async def _load_member(
    session: AsyncSession, member_id: int, household_id: str | None
) -> Member:
    res = await session.execute(
        select(Member).where(
            Member.id == member_id,
            scoped(Member.household_id, household_id),
        )
    )
    member = res.scalar_one_or_none()
    if member is None:
        raise NotFoundError(f"member {member_id} not found")
    return member


async def _load_redemption(
    session: AsyncSession, redemption_id: str, household_id: str | None
) -> Redemption:
    res = await session.execute(
        select(Redemption).where(
            Redemption.id == redemption_id,
            scoped(Redemption.household_id, household_id),
        )
    )
    redemption = res.scalar_one_or_none()
    if redemption is None:
        raise NotFoundError(f"redemption {redemption_id!r} not found")
    return redemption


async def _ensure_stats(
    session: AsyncSession, member_id: int, household_id: str | None
) -> MemberStats:
    """Fetch (or initialise) the member's stats row for in-place arithmetic."""
    res = await session.execute(
        select(MemberStats).where(
            MemberStats.member_id == member_id,
            scoped(MemberStats.household_id, household_id),
        )
    )
    stats = res.scalar_one_or_none()
    if stats is None:
        stats = MemberStats(
            member_id=member_id,
            points_total=0,
            points_this_week=0,
            streak=0,
            bonus_points_total=0,
            household_id=household_id,
        )
        session.add(stats)
        await session.flush()
    return stats


async def _count_redemptions_this_week(
    session: AsyncSession,
    *,
    reward_id: str,
    member_id: int,
    week_anchor: date_type,
    household_id: str | None,
) -> int:
    """Count this member's redemptions of this reward in the current
    week_anchor window. Both pending and approved count toward the cap;
    denied don't (since they were refunded). The cap is per-member-per-
    reward — the scope mirrors how points_this_week is computed."""
    week_start = datetime.combine(week_anchor, datetime.min.time())
    week_end = week_start + timedelta(days=7)
    res = await session.execute(
        select(func.count())
        .select_from(Redemption)
        .where(
            Redemption.reward_id == reward_id,
            Redemption.member_id == member_id,
            Redemption.requested_at >= week_start,
            Redemption.requested_at < week_end,
            Redemption.state.in_(
                [RedemptionState.PENDING_APPROVAL, RedemptionState.APPROVED]
            ),
            scoped(Redemption.household_id, household_id),
        )
    )
    return int(res.scalar_one())


async def request_redemption(
    session: AsyncSession,
    *,
    member_id: int,
    reward_id: str,
    actor: str,
    week_starts_on: str = "monday",
    today: date_type | None = None,
    household_id: str | None = None,
) -> Redemption:
    """Create a `pending_approval` redemption + deduct points.

    Raises `InvalidStateError` if the member can't afford it OR the
    weekly cap on this reward has been reached. Both cases leave the
    member's points untouched.
    """
    member = await _load_member(session, member_id, household_id)
    reward = await _load_reward_active(session, reward_id, household_id)

    stats = await _ensure_stats(session, member.id, household_id)
    current_total = stats.points_total or 0
    if current_total < reward.cost_points:
        raise InvalidStateError(
            f"insufficient points: have {current_total}, need {reward.cost_points}"
        )

    if reward.max_per_week is not None:
        anchor = week_anchor_for(today or utcnow().date(), week_starts_on)
        used = await _count_redemptions_this_week(
            session,
            reward_id=reward.id,
            member_id=member.id,
            week_anchor=anchor,
            household_id=household_id,
        )
        if used >= reward.max_per_week:
            raise InvalidStateError(
                f"weekly cap reached: {used}/{reward.max_per_week} this week"
            )

    # Deduct points. The `bonus_points_total` decrement is what makes
    # the deduction survive the next midnight rollover (F-S001 fix from
    # v0.3.1). The in-memory `points_total` decrement is for immediate
    # UI feedback.
    stats.points_total = max(0, current_total - reward.cost_points)
    stats.bonus_points_total = (stats.bonus_points_total or 0) - reward.cost_points

    redemption = Redemption(
        id=str(uuid.uuid4()),
        household_id=household_id,
        reward_id=reward.id,
        member_id=member.id,
        state=RedemptionState.PENDING_APPROVAL,
        cost_points_at_redeem=reward.cost_points,
        reward_name_at_redeem=reward.name,
        actor_requested=actor,
    )
    session.add(redemption)
    _log(
        session,
        actor=actor,
        action="redemption_requested",
        payload={
            "redemption_id": redemption.id,
            "reward_id": reward.id,
            "reward_name": reward.name,
            "member_id": member.id,
            "cost_points": reward.cost_points,
        },
        household_id=household_id,
    )
    await session.flush()
    return redemption


async def approve_redemption(
    session: AsyncSession,
    redemption_id: str,
    *,
    actor: str,
    now: datetime | None = None,
    household_id: str | None = None,
) -> Redemption:
    """Flip pending → approved. No point change."""
    redemption = await _load_redemption(session, redemption_id, household_id)
    if redemption.state is not RedemptionState.PENDING_APPROVAL:
        raise InvalidStateError(
            f"can only approve PENDING_APPROVAL redemptions; current state is {redemption.state.value}"
        )
    redemption.state = RedemptionState.APPROVED
    redemption.approved_at = now if now is not None else utcnow()
    redemption.approved_by = actor
    _log(
        session,
        actor=actor,
        action="redemption_approved",
        payload={
            "redemption_id": redemption.id,
            "reward_id": redemption.reward_id,
            "member_id": redemption.member_id,
            "cost_points": redemption.cost_points_at_redeem,
        },
        household_id=household_id,
    )
    await session.flush()
    return redemption


async def deny_redemption(
    session: AsyncSession,
    redemption_id: str,
    *,
    actor: str,
    reason: str | None = None,
    now: datetime | None = None,
    household_id: str | None = None,
) -> Redemption:
    """Flip pending → denied. Refund cost via bonus_points_total +=cost.

    Mirrors `points_total` clamp at zero on the in-memory update — but
    note that for a refund (positive delta), the clamp doesn't activate
    unless the existing total was somehow corrupted into negative.
    """
    redemption = await _load_redemption(session, redemption_id, household_id)
    if redemption.state is not RedemptionState.PENDING_APPROVAL:
        raise InvalidStateError(
            f"can only deny PENDING_APPROVAL redemptions; current state is {redemption.state.value}"
        )

    stats = await _ensure_stats(
        session, redemption.member_id, household_id
    )
    stats.bonus_points_total = (
        stats.bonus_points_total or 0
    ) + redemption.cost_points_at_redeem
    stats.points_total = max(
        0, (stats.points_total or 0) + redemption.cost_points_at_redeem
    )

    redemption.state = RedemptionState.DENIED
    redemption.denied_at = now if now is not None else utcnow()
    redemption.denied_by = actor
    redemption.denied_reason = reason

    _log(
        session,
        actor=actor,
        action="redemption_denied",
        payload={
            "redemption_id": redemption.id,
            "reward_id": redemption.reward_id,
            "member_id": redemption.member_id,
            "cost_points_refunded": redemption.cost_points_at_redeem,
            "reason": reason,
        },
        household_id=household_id,
    )
    await session.flush()
    return redemption
