"""Chore CRUD with assignment management."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from family_chores_api.bridge import BridgeProtocol
from family_chores_api.deps import (
    get_bridge,
    get_current_household_id,
    get_effective_timezone,
    get_remote_user,
    get_session,
    get_ws_manager,
    require_parent,
)
from family_chores_api.errors import ConflictError, NotFoundError
from family_chores_api.events import (
    EVT_CHORE_CREATED,
    EVT_CHORE_DELETED,
    EVT_CHORE_UPDATED,
    WSManager,
)
from family_chores_api.schemas import (
    ChoreCreate,
    ChoreCreateResult,
    ChoreRead,
    ChoreUpdate,
    validate_recurrence_config,
)
from family_chores_api.security import ParentClaim
from family_chores_api.services.instance_service import generate_instances
from family_chores_core.naming import normalize_chore_name
from family_chores_core.time import local_today
from family_chores_db.models import ActivityLog, Chore, ChoreTemplate, Member
from family_chores_db.scoped import scoped

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
        template_id=chore.template_id,
    )


def _to_create_result(chore: Chore, template_created: bool) -> ChoreCreateResult:
    """ChoreRead-shaped result + template_created flag for POST responses."""
    base = _to_read(chore)
    return ChoreCreateResult(
        **base.model_dump(),
        template_created=template_created,
    )


async def _load_with_members(
    session: AsyncSession, chore_id: int, household_id: str | None
) -> Chore:
    result = await session.execute(
        select(Chore)
        .where(Chore.id == chore_id, scoped(Chore.household_id, household_id))
        .options(selectinload(Chore.assigned_members))
    )
    chore = result.scalar_one_or_none()
    if chore is None:
        raise NotFoundError(f"chore id {chore_id} not found")
    return chore


async def _resolve_members(
    session: AsyncSession, ids: list[int], household_id: str | None
) -> list[Member]:
    if not ids:
        return []
    result = await session.execute(
        select(Member).where(
            Member.id.in_(ids), scoped(Member.household_id, household_id)
        )
    )
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
    household_id: str | None = Depends(get_current_household_id),
) -> list[ChoreRead]:
    stmt = (
        select(Chore)
        .where(scoped(Chore.household_id, household_id))
        .options(selectinload(Chore.assigned_members))
        .order_by(Chore.name)
    )
    if active is not None:
        stmt = stmt.where(Chore.active.is_(active))
    if member_id is not None:
        stmt = stmt.where(Chore.assigned_members.any(Member.id == member_id))
    result = await session.execute(stmt)
    return [_to_read(c) for c in result.scalars().all()]


@router.get("/{chore_id}", response_model=ChoreRead)
async def get_chore(
    chore_id: int,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> ChoreRead:
    return _to_read(await _load_with_members(session, chore_id, household_id))


@router.post("", response_model=ChoreCreateResult, status_code=status.HTTP_201_CREATED)
async def create_chore(
    body: ChoreCreate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    tz: str = Depends(get_effective_timezone),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> ChoreCreateResult:
    members = await _resolve_members(session, body.assigned_member_ids, household_id)

    # Validate template_id (if provided) against this household's templates.
    # Defense-in-depth — the FK constraint catches non-existent ids, but it
    # would also pass for a real id from a different household and leak
    # state. Per DECISIONS §13: informational only, but still household-scoped.
    if body.template_id is not None:
        existing_template = (
            await session.execute(
                select(ChoreTemplate).where(
                    ChoreTemplate.id == body.template_id,
                    scoped(ChoreTemplate.household_id, household_id),
                )
            )
        ).scalar_one_or_none()
        if existing_template is None:
            raise NotFoundError(f"template id {body.template_id} not found")

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
        household_id=household_id,
        template_id=body.template_id,
        ephemeral=not body.save_as_suggestion,
    )
    chore.assigned_members = members
    session.add(chore)
    await session.flush()

    # Save-as-suggestion flow (DECISIONS §13 §1.1, §5). When the box is
    # checked we either create a fresh template or silently link the chore
    # to a same-named template if one already exists. Either way the chore
    # carries a template_id afterwards (informational), and template_created
    # tells the frontend whether to show the "saved as a suggestion" toast.
    template_created = False
    if body.save_as_suggestion:
        normalized = normalize_chore_name(body.name)
        if normalized:
            existing_match = (
                await session.execute(
                    select(ChoreTemplate).where(
                        scoped(ChoreTemplate.household_id, household_id),
                        ChoreTemplate.name_normalized == normalized,
                    )
                )
            ).scalar_one_or_none()
            if existing_match is None:
                new_template = ChoreTemplate(
                    id=str(uuid.uuid4()),
                    household_id=household_id,
                    name=body.name,
                    name_normalized=normalized,
                    icon=body.icon,
                    category=None,
                    age_min=None,
                    age_max=None,
                    points_suggested=body.points,
                    default_recurrence_type=body.recurrence_type,
                    default_recurrence_config=body.recurrence_config,
                    description=body.description,
                    source="custom",
                    starter_key=None,
                )
                session.add(new_template)
                await session.flush()
                if chore.template_id is None:
                    chore.template_id = new_template.id
                template_created = True
            elif chore.template_id is None:
                # Silent dedup: link the chore to the existing template.
                chore.template_id = existing_match.id

    session.add(
        ActivityLog(
            actor=user,
            action="chore_created",
            payload={"id": chore.id, "name": chore.name},
            household_id=household_id,
        )
    )
    # So today's instance exists the moment the chore is created — users
    # shouldn't have to wait for midnight rollover to see their new chore.
    await generate_instances(session, today=local_today(tz), household_id=household_id)
    await session.commit()
    for m in members:
        bridge.notify_member_dirty(m.id)
    await ws.broadcast({"type": EVT_CHORE_CREATED, "chore_id": chore.id})
    chore = await _load_with_members(session, chore.id, household_id)
    return _to_create_result(chore, template_created=template_created)


@router.patch("/{chore_id}", response_model=ChoreRead)
async def update_chore(
    chore_id: int,
    body: ChoreUpdate,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    tz: str = Depends(get_effective_timezone),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> ChoreRead:
    chore = await _load_with_members(session, chore_id, household_id)

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
        members = await _resolve_members(session, assignment_ids, household_id)
        chore.assigned_members = members
        changes["assigned_member_ids"] = sorted(m.id for m in members)

    if changes:
        session.add(
            ActivityLog(
                actor=user,
                action="chore_updated",
                payload={"id": chore.id, "changes": changes},
                household_id=household_id,
            )
        )
    # Regenerate so new assignments / newly-active chores get today-onwards
    # instances without waiting for the midnight rollover.
    await generate_instances(session, today=local_today(tz), household_id=household_id)
    await session.commit()
    chore = await _load_with_members(session, chore.id, household_id)
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
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> None:
    chore = await _load_with_members(session, chore_id, household_id)
    affected_member_ids = [m.id for m in chore.assigned_members]
    session.add(
        ActivityLog(
            actor=user,
            action="chore_deleted",
            payload={"id": chore.id, "name": chore.name},
            household_id=household_id,
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
