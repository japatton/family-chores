"""Family-member CRUD + per-kid PIN endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from family_chores_api.bridge import BridgeProtocol
from family_chores_api.deps import (
    get_bridge,
    get_calendar_cache,
    get_current_household_id,
    get_remote_user,
    get_session,
    get_ws_manager,
    require_parent,
)
from family_chores_api.errors import (
    ConflictError,
    NotFoundError,
    PinInvalidError,
    PinNotSetError,
)
from family_chores_api.events import (
    EVT_MEMBER_CREATED,
    EVT_MEMBER_DELETED,
    EVT_MEMBER_UPDATED,
    WSManager,
)
from family_chores_api.schemas import (
    MemberCreate,
    MemberPinSetRequest,
    MemberPinStatus,
    MemberPinVerifyRequest,
    MemberPinVerifyResponse,
    MemberRead,
    MemberStatsRead,
    MemberUpdate,
)
from family_chores_api.security import ParentClaim, hash_pin, verify_pin
from family_chores_api.services.calendar import CalendarCache
from family_chores_db.models import ActivityLog, Member, MemberStats
from family_chores_db.scoped import scoped

router = APIRouter(prefix="/api/members", tags=["members"])

# Per-kid PIN unlock window. Short enough that an unattended tablet
# doesn't expose the member view all day; long enough that a kid
# doesn't have to re-PIN every time they tap a chore. Mirrored in
# the response payload so the SPA computes its own re-verify time.
_KID_PIN_WINDOW_SECONDS = 60 * 60  # 1 hour


def _to_read(member: Member, stats: MemberStats | None) -> MemberRead:
    stats_payload = MemberStatsRead(
        points_total=stats.points_total if stats else 0,
        points_this_week=stats.points_this_week if stats else 0,
        week_anchor=stats.week_anchor if stats else None,
        streak=stats.streak if stats else 0,
        last_all_done_date=stats.last_all_done_date if stats else None,
    )
    return MemberRead(
        id=member.id,
        name=member.name,
        slug=member.slug,
        avatar=member.avatar,
        color=member.color,
        display_mode=member.display_mode,
        requires_approval=member.requires_approval,
        ha_todo_entity_id=member.ha_todo_entity_id,
        # `member.calendar_entity_ids` defaults to `[]` via the column
        # server_default; it can also be `None` for rows created in
        # tests that bypass the model default. Normalise.
        calendar_entity_ids=list(member.calendar_entity_ids or []),
        stats=stats_payload,
        pin_set=member.pin_hash is not None,
    )


async def _load_by_slug(
    session: AsyncSession, slug: str, household_id: str | None
) -> Member:
    result = await session.execute(
        select(Member)
        .where(Member.slug == slug, scoped(Member.household_id, household_id))
        .options(selectinload(Member.stats))
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise NotFoundError(f"member {slug!r} not found")
    return member


@router.get("", response_model=list[MemberRead])
async def list_members(
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> list[MemberRead]:
    result = await session.execute(
        select(Member)
        .where(scoped(Member.household_id, household_id))
        .options(selectinload(Member.stats))
        .order_by(Member.name)
    )
    return [_to_read(m, m.stats) for m in result.scalars().all()]


@router.get("/{slug}", response_model=MemberRead)
async def get_member(
    slug: str,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> MemberRead:
    m = await _load_by_slug(session, slug, household_id)
    return _to_read(m, m.stats)


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def create_member(
    body: MemberCreate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> MemberRead:
    dupe = await session.execute(
        select(Member).where(
            Member.slug == body.slug, scoped(Member.household_id, household_id)
        )
    )
    if dupe.scalar_one_or_none() is not None:
        raise ConflictError(f"member slug {body.slug!r} already exists")

    member = Member(
        name=body.name,
        slug=body.slug,
        avatar=body.avatar,
        color=body.color,
        display_mode=body.display_mode,
        requires_approval=body.requires_approval,
        ha_todo_entity_id=body.ha_todo_entity_id,
        calendar_entity_ids=list(body.calendar_entity_ids),
        household_id=household_id,
    )
    session.add(member)
    await session.flush()
    stats = MemberStats(
        member_id=member.id,
        points_total=0,
        points_this_week=0,
        streak=0,
        household_id=household_id,
    )
    session.add(stats)
    session.add(
        ActivityLog(
            actor=user,
            action="member_created",
            payload={"id": member.id, "slug": member.slug, "name": member.name},
            household_id=household_id,
        )
    )
    await session.commit()
    bridge.notify_member_dirty(member.id)
    await ws.broadcast({"type": EVT_MEMBER_CREATED, "member_id": member.id})
    return _to_read(member, stats)


@router.patch("/{slug}", response_model=MemberRead)
async def update_member(
    slug: str,
    body: MemberUpdate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    cache: CalendarCache = Depends(get_calendar_cache),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> MemberRead:
    member = await _load_by_slug(session, slug, household_id)

    changes: dict[str, object] = {}
    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(member, field_name, value)
        changes[field_name] = value

    if changes:
        session.add(
            ActivityLog(
                actor=user,
                action="member_updated",
                payload={"id": member.id, "slug": member.slug, "changes": changes},
                household_id=household_id,
            )
        )
    await session.commit()
    # If the calendar mapping changed, drop the calendar cache so the
    # next read sees the new entity set immediately (DECISIONS §14
    # Q10 — config edits should bypass the 60s TTL).
    if "calendar_entity_ids" in changes:
        await cache.invalidate()
    bridge.notify_member_dirty(member.id)
    await ws.broadcast({"type": EVT_MEMBER_UPDATED, "member_id": member.id})
    return _to_read(member, member.stats)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    # FastAPI infers `response_model = NoneType` from the `-> None`
    # annotation, which is truthy and trips its "204 must not have a
    # body" assertion. Explicit None overrides the inference.
    response_model=None,
)
async def delete_member(
    slug: str,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> None:
    member = await _load_by_slug(session, slug, household_id)
    member_id = member.id
    session.add(
        ActivityLog(
            actor=user,
            action="member_deleted",
            payload={"id": member_id, "slug": slug, "name": member.name},
            household_id=household_id,
        )
    )
    await session.delete(member)
    await session.commit()
    await ws.broadcast({"type": EVT_MEMBER_DELETED, "member_id": member_id})


# ─── per-kid PIN (DECISIONS §17) ──────────────────────────────────────────


@router.get("/{slug}/pin", response_model=MemberPinStatus)
async def get_member_pin_status(
    slug: str,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> MemberPinStatus:
    """Whether this member has a PIN set. No auth required — the answer
    is also surfaced on `MemberRead.pin_set`, but this endpoint exists so
    the SPA can poll without needing the full member payload."""
    member = await _load_by_slug(session, slug, household_id)
    return MemberPinStatus(
        member_id=member.id, slug=member.slug, pin_set=member.pin_hash is not None
    )


@router.post("/{slug}/pin/set", response_model=MemberRead, status_code=200)
async def set_member_pin(
    slug: str,
    body: MemberPinSetRequest,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> MemberRead:
    """Parent sets (or rotates) the per-kid PIN. Always overwrites — no
    `current_pin` proof-of-knowledge step like the parent PIN, because a
    parent who forgot their kid's PIN would otherwise be unable to reset
    it without the parent-PIN admin path. Parent already has elevated
    auth via `require_parent`."""
    member = await _load_by_slug(session, slug, household_id)
    member.pin_hash = hash_pin(body.pin)
    session.add(
        ActivityLog(
            actor=user,
            action="member_pin_set",
            payload={"id": member.id, "slug": member.slug},
            household_id=household_id,
        )
    )
    await session.commit()
    await ws.broadcast({"type": EVT_MEMBER_UPDATED, "member_id": member.id})
    return _to_read(member, member.stats)


@router.post("/{slug}/pin/verify", response_model=MemberPinVerifyResponse)
async def verify_member_pin(
    slug: str,
    body: MemberPinVerifyRequest,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> MemberPinVerifyResponse:
    """Kid-facing — no parent JWT required. Returns the verified-until
    timestamp on success (the SPA tracks per-member unlock state in
    client-side storage; the server doesn't issue a token)."""
    member = await _load_by_slug(session, slug, household_id)
    if member.pin_hash is None:
        raise PinNotSetError(f"member {slug!r} has no PIN set")
    if not verify_pin(body.pin, member.pin_hash):
        raise PinInvalidError("incorrect PIN")
    return MemberPinVerifyResponse(
        member_id=member.id,
        verified_until=int(time.time()) + _KID_PIN_WINDOW_SECONDS,
    )


@router.post(
    "/{slug}/pin/clear",
    response_model=MemberRead,
    status_code=200,
)
async def clear_member_pin(
    slug: str,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> MemberRead:
    """Parent removes the per-kid PIN. Returns the updated member."""
    member = await _load_by_slug(session, slug, household_id)
    if member.pin_hash is None:
        # Idempotent — clearing an already-cleared PIN is fine.
        return _to_read(member, member.stats)
    member.pin_hash = None
    session.add(
        ActivityLog(
            actor=user,
            action="member_pin_cleared",
            payload={"id": member.id, "slug": member.slug},
            household_id=household_id,
        )
    )
    await session.commit()
    await ws.broadcast({"type": EVT_MEMBER_UPDATED, "member_id": member.id})
    return _to_read(member, member.stats)
