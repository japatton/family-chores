"""Rewards catalogue + redemption flow.

Two route surfaces under one module (the operations are tightly
coupled — rewards exist to be redeemed):

  /api/rewards/                   GET (kid-visible) / POST (parent)
  /api/rewards/{id}               GET / PATCH (parent) / DELETE (parent → soft delete)
  /api/members/{slug}/redemptions GET / POST (kid-facing)
  /api/redemptions                GET ?state=...
  /api/redemptions/{id}/approve   POST (parent)
  /api/redemptions/{id}/deny      POST (parent) — body: optional reason

State machine + point integration lives in
`family_chores_api.services.redemption_service`. The router is just
HTTP plumbing + activity-log + WS broadcast + HA event firing.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_api.bridge import BridgeProtocol
from family_chores_api.deps import (
    get_bridge,
    get_current_household_id,
    get_effective_timezone,
    get_remote_user,
    get_session,
    get_week_starts_on,
    get_ws_manager,
    require_parent,
)
from family_chores_api.errors import NotFoundError
from family_chores_api.events import WSManager
from family_chores_api.schemas import (
    RedemptionCreate,
    RedemptionDenyRequest,
    RedemptionRead,
    RewardCreate,
    RewardRead,
    RewardUpdate,
)
from family_chores_api.security import ParentClaim
from family_chores_api.services.redemption_service import (
    approve_redemption,
    deny_redemption,
    request_redemption,
)
from family_chores_core.time import local_today
from family_chores_db.models import (
    ActivityLog,
    Member,
    Redemption,
    RedemptionState,
    Reward,
)
from family_chores_db.scoped import scoped

# Two routers under one module so the URL prefixes can stay flat. They're
# registered together in the api app factory.

rewards_router = APIRouter(prefix="/api/rewards", tags=["rewards"])
redemptions_router = APIRouter(prefix="/api/redemptions", tags=["redemptions"])
member_redemptions_router = APIRouter(
    prefix="/api/members", tags=["redemptions"]
)


# Event names — wired into the HA bridge for automation hooks.
EVT_REWARD_CREATED = "reward_created"
EVT_REWARD_UPDATED = "reward_updated"
EVT_REWARD_DELETED = "reward_deleted"
EVT_REDEMPTION_REQUESTED = "redemption_requested"
EVT_REDEMPTION_APPROVED = "redemption_approved"
EVT_REDEMPTION_DENIED = "redemption_denied"

_HA_EVENT_REDEMPTION_REQUESTED = "family_chores_redemption_requested"
_HA_EVENT_REDEMPTION_APPROVED = "family_chores_redemption_approved"
_HA_EVENT_REDEMPTION_DENIED = "family_chores_redemption_denied"


# ─── helpers ──────────────────────────────────────────────────────────────


async def _load_reward(
    session: AsyncSession,
    reward_id: str,
    household_id: str | None,
    *,
    include_inactive: bool = True,
) -> Reward:
    stmt = select(Reward).where(
        Reward.id == reward_id,
        scoped(Reward.household_id, household_id),
    )
    if not include_inactive:
        stmt = stmt.where(Reward.active.is_(True))
    res = await session.execute(stmt)
    reward = res.scalar_one_or_none()
    if reward is None:
        raise NotFoundError(f"reward {reward_id!r} not found")
    return reward


async def _load_member_by_slug(
    session: AsyncSession, slug: str, household_id: str | None
) -> Member:
    res = await session.execute(
        select(Member).where(
            Member.slug == slug, scoped(Member.household_id, household_id)
        )
    )
    member = res.scalar_one_or_none()
    if member is None:
        raise NotFoundError(f"member {slug!r} not found")
    return member


# ─── /api/rewards ─────────────────────────────────────────────────────────


@rewards_router.get("", response_model=list[RewardRead])
async def list_rewards(
    active: bool | None = None,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> list[RewardRead]:
    """Kid-visible. Default returns only active rewards (the catalogue
    that can actually be redeemed). Parents who want to see retired rows
    pass `?active=false` (or `?active` omitted with explicit query)."""
    stmt = select(Reward).where(scoped(Reward.household_id, household_id))
    if active is not None:
        stmt = stmt.where(Reward.active.is_(active))
    else:
        stmt = stmt.where(Reward.active.is_(True))
    stmt = stmt.order_by(Reward.cost_points, Reward.name)
    result = await session.execute(stmt)
    return [RewardRead.model_validate(r) for r in result.scalars().all()]


@rewards_router.get("/{reward_id}", response_model=RewardRead)
async def get_reward(
    reward_id: str,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> RewardRead:
    reward = await _load_reward(session, reward_id, household_id)
    return RewardRead.model_validate(reward)


@rewards_router.post("", response_model=RewardRead, status_code=status.HTTP_201_CREATED)
async def create_reward(
    body: RewardCreate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> RewardRead:
    reward = Reward(
        id=str(uuid.uuid4()),
        household_id=household_id,
        name=body.name,
        description=body.description,
        cost_points=body.cost_points,
        icon=body.icon,
        active=body.active,
        max_per_week=body.max_per_week,
    )
    session.add(reward)
    session.add(
        ActivityLog(
            actor=user,
            action="reward_created",
            payload={"id": reward.id, "name": reward.name},
            household_id=household_id,
        )
    )
    await session.commit()
    await session.refresh(reward)
    await ws.broadcast({"type": EVT_REWARD_CREATED, "reward_id": reward.id})
    return RewardRead.model_validate(reward)


@rewards_router.patch("/{reward_id}", response_model=RewardRead)
async def update_reward(
    reward_id: str,
    body: RewardUpdate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> RewardRead:
    reward = await _load_reward(session, reward_id, household_id)
    updates = body.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        setattr(reward, field_name, value)
    session.add(
        ActivityLog(
            actor=user,
            action="reward_updated",
            payload={"id": reward.id, "changes": updates},
            household_id=household_id,
        )
    )
    await session.commit()
    await session.refresh(reward)
    await ws.broadcast({"type": EVT_REWARD_UPDATED, "reward_id": reward.id})
    return RewardRead.model_validate(reward)


@rewards_router.delete("/{reward_id}")
async def delete_reward(
    reward_id: str,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> Response:
    """Soft delete (active=False). The reward stays in the DB so
    historical redemption rows keep their RESTRICT FK valid; it just
    drops out of the kid-visible catalogue.

    Hard delete isn't supported — soft is intentional; see the
    Redemption model docstring for the audit-trail rationale."""
    reward = await _load_reward(session, reward_id, household_id)
    if reward.active:
        reward.active = False
        session.add(
            ActivityLog(
                actor=user,
                action="reward_deleted",
                payload={"id": reward.id, "name": reward.name},
                household_id=household_id,
            )
        )
        await session.commit()
        await ws.broadcast({"type": EVT_REWARD_DELETED, "reward_id": reward.id})
    return Response(status_code=204)


# ─── /api/members/{slug}/redemptions (kid-facing) ─────────────────────────


@member_redemptions_router.get(
    "/{slug}/redemptions", response_model=list[RedemptionRead]
)
async def list_member_redemptions(
    slug: str,
    state: RedemptionState | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> list[RedemptionRead]:
    """Kid-visible (and parent-visible). Returns this member's
    redemptions, newest first. Default limit 50; bump for activity-log
    style views."""
    member = await _load_member_by_slug(session, slug, household_id)
    stmt = (
        select(Redemption)
        .where(
            Redemption.member_id == member.id,
            scoped(Redemption.household_id, household_id),
        )
        .order_by(Redemption.requested_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    if state is not None:
        stmt = stmt.where(Redemption.state == state)
    res = await session.execute(stmt)
    return [RedemptionRead.model_validate(r) for r in res.scalars().all()]


@member_redemptions_router.post(
    "/{slug}/redemptions",
    response_model=RedemptionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_redemption(
    slug: str,
    body: RedemptionCreate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    tz: str = Depends(get_effective_timezone),
    week_starts_on: str = Depends(get_week_starts_on),
    household_id: str | None = Depends(get_current_household_id),
) -> RedemptionRead:
    """Kid-facing (no parent JWT required). Validates the reward is
    active + the member can afford it + the weekly cap (if any) hasn't
    been hit, then creates a pending_approval row and deducts points."""
    member = await _load_member_by_slug(session, slug, household_id)
    redemption = await request_redemption(
        session,
        member_id=member.id,
        reward_id=body.reward_id,
        actor=user,
        week_starts_on=week_starts_on,
        today=local_today(tz),
        household_id=household_id,
    )
    await session.commit()
    await session.refresh(redemption)
    # Member's points just changed → republish their sensors.
    bridge.notify_member_dirty(member.id)
    bridge.enqueue_event(
        _HA_EVENT_REDEMPTION_REQUESTED,
        {
            "redemption_id": redemption.id,
            "reward_id": redemption.reward_id,
            "reward_name": redemption.reward_name_at_redeem,
            "member_id": redemption.member_id,
            "cost_points": redemption.cost_points_at_redeem,
        },
    )
    await ws.broadcast(
        {"type": EVT_REDEMPTION_REQUESTED, "redemption_id": redemption.id}
    )
    return RedemptionRead.model_validate(redemption)


# ─── /api/redemptions (parent queue + approve/deny) ───────────────────────


@redemptions_router.get("", response_model=list[RedemptionRead])
async def list_redemptions(
    state: RedemptionState | None = None,
    member_id: int | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> list[RedemptionRead]:
    """Cross-member redemption list (the parent queue). Default returns
    everything; pass `?state=pending_approval` for the queue view, or
    `?member_id=N` to scope to one member."""
    stmt = (
        select(Redemption)
        .where(scoped(Redemption.household_id, household_id))
        .order_by(Redemption.requested_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    if state is not None:
        stmt = stmt.where(Redemption.state == state)
    if member_id is not None:
        stmt = stmt.where(Redemption.member_id == member_id)
    res = await session.execute(stmt)
    return [RedemptionRead.model_validate(r) for r in res.scalars().all()]


@redemptions_router.post(
    "/{redemption_id}/approve", response_model=RedemptionRead
)
async def approve(
    redemption_id: str,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> RedemptionRead:
    redemption = await approve_redemption(
        session, redemption_id, actor=user, household_id=household_id
    )
    await session.commit()
    await session.refresh(redemption)
    bridge.enqueue_event(
        _HA_EVENT_REDEMPTION_APPROVED,
        {
            "redemption_id": redemption.id,
            "reward_id": redemption.reward_id,
            "reward_name": redemption.reward_name_at_redeem,
            "member_id": redemption.member_id,
            "cost_points": redemption.cost_points_at_redeem,
        },
    )
    await ws.broadcast(
        {"type": EVT_REDEMPTION_APPROVED, "redemption_id": redemption.id}
    )
    return RedemptionRead.model_validate(redemption)


@redemptions_router.post("/{redemption_id}/deny", response_model=RedemptionRead)
async def deny(
    redemption_id: str,
    body: RedemptionDenyRequest,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> RedemptionRead:
    redemption = await deny_redemption(
        session,
        redemption_id,
        actor=user,
        reason=body.reason,
        household_id=household_id,
    )
    await session.commit()
    await session.refresh(redemption)
    # Refund changed the member's points → republish their sensors.
    bridge.notify_member_dirty(redemption.member_id)
    bridge.enqueue_event(
        _HA_EVENT_REDEMPTION_DENIED,
        {
            "redemption_id": redemption.id,
            "reward_id": redemption.reward_id,
            "reward_name": redemption.reward_name_at_redeem,
            "member_id": redemption.member_id,
            "cost_points_refunded": redemption.cost_points_at_redeem,
            "reason": body.reason,
        },
    )
    await ws.broadcast(
        {"type": EVT_REDEMPTION_DENIED, "redemption_id": redemption.id}
    )
    return RedemptionRead.model_validate(redemption)


# Re-export consumed by routers/__init__ + app.py.
__all__ = [
    "EVT_REDEMPTION_APPROVED",
    "EVT_REDEMPTION_DENIED",
    "EVT_REDEMPTION_REQUESTED",
    "EVT_REWARD_CREATED",
    "EVT_REWARD_DELETED",
    "EVT_REWARD_UPDATED",
    "member_redemptions_router",
    "redemptions_router",
    "rewards_router",
]
