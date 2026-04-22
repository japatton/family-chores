"""Family-member CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from family_chores.api.deps import (
    get_bridge,
    get_remote_user,
    get_session,
    get_ws_manager,
    require_parent,
)
from family_chores.api.errors import ConflictError, NotFoundError
from family_chores.api.events import (
    EVT_MEMBER_CREATED,
    EVT_MEMBER_DELETED,
    EVT_MEMBER_UPDATED,
    WSManager,
)
from family_chores.api.schemas import (
    MemberCreate,
    MemberRead,
    MemberStatsRead,
    MemberUpdate,
)
from family_chores.db.models import ActivityLog, Member, MemberStats
from family_chores.ha.bridge import BridgeProtocol

router = APIRouter(prefix="/api/members", tags=["members"])


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
        stats=stats_payload,
    )


async def _load_by_slug(session: AsyncSession, slug: str) -> Member:
    result = await session.execute(
        select(Member).where(Member.slug == slug).options(selectinload(Member.stats))
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise NotFoundError(f"member {slug!r} not found")
    return member


@router.get("", response_model=list[MemberRead])
async def list_members(session: AsyncSession = Depends(get_session)) -> list[MemberRead]:
    result = await session.execute(
        select(Member).options(selectinload(Member.stats)).order_by(Member.name)
    )
    return [_to_read(m, m.stats) for m in result.scalars().all()]


@router.get("/{slug}", response_model=MemberRead)
async def get_member(slug: str, session: AsyncSession = Depends(get_session)) -> MemberRead:
    m = await _load_by_slug(session, slug)
    return _to_read(m, m.stats)


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def create_member(
    body: MemberCreate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    _parent=Depends(require_parent),
) -> MemberRead:
    dupe = await session.execute(select(Member).where(Member.slug == body.slug))
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
    )
    session.add(member)
    await session.flush()
    stats = MemberStats(
        member_id=member.id, points_total=0, points_this_week=0, streak=0
    )
    session.add(stats)
    session.add(
        ActivityLog(
            actor=user,
            action="member_created",
            payload={"id": member.id, "slug": member.slug, "name": member.name},
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
    _parent=Depends(require_parent),
) -> MemberRead:
    member = await _load_by_slug(session, slug)

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
            )
        )
    await session.commit()
    bridge.notify_member_dirty(member.id)
    await ws.broadcast({"type": EVT_MEMBER_UPDATED, "member_id": member.id})
    return _to_read(member, member.stats)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(
    slug: str,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    _parent=Depends(require_parent),
) -> None:
    member = await _load_by_slug(session, slug)
    member_id = member.id
    session.add(
        ActivityLog(
            actor=user,
            action="member_deleted",
            payload={"id": member_id, "slug": slug, "name": member.name},
        )
    )
    await session.delete(member)
    await session.commit()
    await ws.broadcast({"type": EVT_MEMBER_DELETED, "member_id": member_id})
