"""Chore CRUD with assignment management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from family_chores.api.deps import (
    get_bridge,
    get_effective_timezone,
    get_options,
    get_remote_user,
    get_session,
    get_ws_manager,
    require_parent,
)
from family_chores.api.errors import ConflictError, NotFoundError
from family_chores.api.events import (
    EVT_CHORE_CREATED,
    EVT_CHORE_DELETED,
    EVT_CHORE_UPDATED,
    WSManager,
)
from family_chores.api.schemas import (
    ChoreCreate,
    ChoreRead,
    ChoreUpdate,
    validate_recurrence_config,
)
from family_chores.config import Options
from family_chores.core.time import local_today
from family_chores.db.models import ActivityLog, Chore, Member
from family_chores.ha.bridge import BridgeProtocol
from family_chores.security import ParentClaim
from family_chores.services.instance_service import generate_instances

router = APIRouter(prefix="/api/chores", tags=["chores"])


def _to_read(chore: Chore) -> ChoreRead:
    return ChoreRead(
        id=chore.id,
        name=chore.name,
        icon=chore.icon,
        points=chore.points,
        description=chore.description,
        image=chore.image,
        active=chore.active,
        recurrence_type=chore.recurrence_type,
        recurrence_config=chore.recurrence_config,
        time_window_start=chore.time_window_start,
        time_window_end=chore.time_window_end,
        assigned_member_ids=sorted(m.id for m in chore.assigned_members),
    )


async def _load_with_members(session: AsyncSession, chore_id: int) -> Chore:
    result = await session.execute(
        select(Chore)
        .where(Chore.id == chore_id)
        .options(selectinload(Chore.assigned_members))
    )
    chore = result.scalar_one_or_none()
    if chore is None:
        raise NotFoundError(f"chore id {chore_id} not found")
    return chore


async def _resolve_members(session: AsyncSession, ids: list[int]) -> list[Member]:
    if not ids:
        return []
    result = await session.execute(select(Member).where(Member.id.in_(ids)))
    members = result.scalars().all()
    found = {m.id for m in members}
    missing = [i for i in ids if i not in found]
    if missing:
        raise NotFoundError(f"members not found: {missing}")
    return list(members)


@router.get("", response_model=list[ChoreRead])
async def list_chores(
    active: bool | None = None,
    member_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ChoreRead]:
    stmt = select(Chore).options(selectinload(Chore.assigned_members)).order_by(Chore.name)
    if active is not None:
        stmt = stmt.where(Chore.active.is_(active))
    if member_id is not None:
        stmt = stmt.where(Chore.assigned_members.any(Member.id == member_id))
    result = await session.execute(stmt)
    return [_to_read(c) for c in result.scalars().all()]


@router.get("/{chore_id}", response_model=ChoreRead)
async def get_chore(chore_id: int, session: AsyncSession = Depends(get_session)) -> ChoreRead:
    return _to_read(await _load_with_members(session, chore_id))


@router.post("", response_model=ChoreRead, status_code=status.HTTP_201_CREATED)
async def create_chore(
    body: ChoreCreate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    opts: Options = Depends(get_options),
    tz: str = Depends(get_effective_timezone),
    _parent: ParentClaim = Depends(require_parent),
) -> ChoreRead:
    members = await _resolve_members(session, body.assigned_member_ids)
    chore = Chore(
        name=body.name,
        icon=body.icon,
        points=body.points,
        description=body.description,
        image=body.image,
        active=body.active,
        recurrence_type=body.recurrence_type,
        recurrence_config=body.recurrence_config,
        time_window_start=body.time_window_start,
        time_window_end=body.time_window_end,
    )
    chore.assigned_members = members
    session.add(chore)
    await session.flush()
    session.add(
        ActivityLog(
            actor=user,
            action="chore_created",
            payload={"id": chore.id, "name": chore.name},
        )
    )
    # So today's instance exists the moment the chore is created — users
    # shouldn't have to wait for midnight rollover to see their new chore.
    await generate_instances(session, today=local_today(tz))
    await session.commit()
    for m in members:
        bridge.notify_member_dirty(m.id)
    await ws.broadcast({"type": EVT_CHORE_CREATED, "chore_id": chore.id})
    chore = await _load_with_members(session, chore.id)
    return _to_read(chore)


@router.patch("/{chore_id}", response_model=ChoreRead)
async def update_chore(
    chore_id: int,
    body: ChoreUpdate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    opts: Options = Depends(get_options),
    tz: str = Depends(get_effective_timezone),
    _parent: ParentClaim = Depends(require_parent),
) -> ChoreRead:
    chore = await _load_with_members(session, chore_id)

    updates = body.model_dump(exclude_unset=True)

    # Validate recurrence_config against the (possibly new) recurrence_type.
    if "recurrence_type" in updates or "recurrence_config" in updates:
        target_type = updates.get("recurrence_type", chore.recurrence_type)
        target_cfg = updates.get("recurrence_config", chore.recurrence_config)
        try:
            cleaned = validate_recurrence_config(target_type, target_cfg or {})
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        updates["recurrence_config"] = cleaned

    assignment_ids = updates.pop("assigned_member_ids", None)

    changes: dict[str, object] = {}
    for field_name, value in updates.items():
        setattr(chore, field_name, value)
        changes[field_name] = value

    if assignment_ids is not None:
        members = await _resolve_members(session, assignment_ids)
        chore.assigned_members = members
        changes["assigned_member_ids"] = sorted(m.id for m in members)

    if changes:
        session.add(
            ActivityLog(
                actor=user,
                action="chore_updated",
                payload={"id": chore.id, "changes": changes},
            )
        )
    # Regenerate so new assignments / newly-active chores get today-onwards
    # instances without waiting for the midnight rollover.
    await generate_instances(session, today=local_today(tz))
    await session.commit()
    chore = await _load_with_members(session, chore.id)
    for m in chore.assigned_members:
        bridge.notify_member_dirty(m.id)
    await ws.broadcast({"type": EVT_CHORE_UPDATED, "chore_id": chore.id})
    return _to_read(chore)


@router.delete(
    "/{chore_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # FastAPI infers `response_model = NoneType` from the `-> None`
    # annotation, which trips its "204 must not have a body" assertion.
    # Explicit None overrides the inference.
    response_model=None,
)
async def delete_chore(
    chore_id: int,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    _parent: ParentClaim = Depends(require_parent),
) -> None:
    chore = await _load_with_members(session, chore_id)
    affected_member_ids = [m.id for m in chore.assigned_members]
    session.add(
        ActivityLog(
            actor=user,
            action="chore_deleted",
            payload={"id": chore.id, "name": chore.name},
        )
    )
    await session.delete(chore)
    await session.commit()
    for mid in affected_member_ids:
        bridge.notify_member_dirty(mid)
    # Orphan todo items are cleaned up by the 15-min reconciler; the
    # DB cascade already removed chore_instances so we can't call
    # bridge.notify_instance_changed on specific rows.
    await ws.broadcast({"type": EVT_CHORE_DELETED, "chore_id": chore_id})
