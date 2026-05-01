"""Per-instance state transitions + the "today" aggregate view.

Each transition:
  1. Runs the pure state change in `services.instance_actions`.
  2. Recomputes the affected member's stats inline so the response body
     (and the `/today` view) reflect the new totals immediately.
  3. Commits.
  4. Notifies the HA bridge (member sensors + todo item + approvals count)
     and fires the relevant `family_chores_*` event.
  5. Broadcasts a `instance_updated` WebSocket event.

The `/today` view is also the kid-facing surface for calendar events
(DECISIONS §14): each `TodayMember` carries `calendar_events` for the
day (post hide-past filter) so the parent's home and the kid view can
both render "what's happening today" without a separate API roundtrip.
"""

from __future__ import annotations

import logging
from datetime import UTC, date as date_type, datetime, time as time_type, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from zoneinfo import ZoneInfo

from family_chores_api.bridge import BridgeProtocol
from family_chores_api.deps import (
    get_bridge,
    get_calendar_cache,
    get_calendar_provider,
    get_current_household_id,
    get_effective_timezone,
    get_remote_user,
    get_session,
    get_week_starts_on,
    get_ws_manager,
    require_parent,
)
from family_chores_api.errors import NotFoundError
from family_chores_api.events import EVT_INSTANCE_UPDATED, WSManager
from family_chores_api.schemas import (
    AdjustPointsRequest,
    CalendarEventRead,
    InstanceRead,
    MemberStatsRead,
    RejectRequest,
    TodayInstance,
    TodayMember,
    TodayView,
)
from family_chores_api.services.calendar import (
    CalendarCache,
    CalendarEvent,
    CalendarProvider,
    get_events_for_window,
    hide_past,
    partition_by_member,
)
from family_chores_api.security import ParentClaim
from family_chores_api.services.instance_actions import (
    adjust_member_points,
    approve_instance,
    complete_instance,
    reject_instance,
    skip_instance,
    undo_complete,
)
from family_chores_api.services.stats_service import recompute_stats_for_member
from family_chores_core.time import local_today
from family_chores_db.models import (
    Chore,
    ChoreInstance,
    HouseholdSettings,
    InstanceState,
    Member,
)
from family_chores_db.scoped import scoped

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["instances"])

_instance_router = APIRouter(prefix="/instances")


EVENT_COMPLETED = "family_chores_completed"
EVENT_APPROVED = "family_chores_approved"


@_instance_router.get("", response_model=list[InstanceRead])
async def list_instances(
    member_id: int | None = None,
    chore_id: int | None = None,
    state: InstanceState | None = None,
    from_: date_type | None = Query(None, alias="from"),
    to: date_type | None = None,
    limit: int = Query(200, ge=1, le=1000),
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> list[InstanceRead]:
    stmt = (
        select(ChoreInstance)
        .where(scoped(ChoreInstance.household_id, household_id))
        .order_by(ChoreInstance.date.desc(), ChoreInstance.id.desc())
    )
    if member_id is not None:
        stmt = stmt.where(ChoreInstance.member_id == member_id)
    if chore_id is not None:
        stmt = stmt.where(ChoreInstance.chore_id == chore_id)
    if state is not None:
        stmt = stmt.where(ChoreInstance.state == state)
    if from_ is not None:
        stmt = stmt.where(ChoreInstance.date >= from_)
    if to is not None:
        stmt = stmt.where(ChoreInstance.date <= to)
    stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return [InstanceRead.model_validate(r) for r in result.scalars().all()]


@_instance_router.get("/{instance_id}", response_model=InstanceRead)
async def get_instance(
    instance_id: int,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> InstanceRead:
    res = await session.execute(
        select(ChoreInstance).where(
            ChoreInstance.id == instance_id,
            scoped(ChoreInstance.household_id, household_id),
        )
    )
    inst = res.scalar_one_or_none()
    if inst is None:
        raise NotFoundError(f"instance {instance_id} not found")
    return InstanceRead.model_validate(inst)


async def _finalize_action(
    session: AsyncSession,
    inst: ChoreInstance,
    *,
    week_starts_on: str,
    tz: str,
    household_id: str | None,
) -> None:
    today = local_today(tz)
    await recompute_stats_for_member(
        session,
        inst.member_id,
        today=today,
        week_starts_on=week_starts_on,
        household_id=household_id,
    )
    await session.commit()


def _notify_bridge(
    bridge: BridgeProtocol,
    inst: ChoreInstance,
    *,
    event: str | None = None,
) -> None:
    bridge.notify_instance_changed(inst.id)
    bridge.notify_member_dirty(inst.member_id)
    bridge.notify_approvals_dirty()
    if event is not None:
        bridge.enqueue_event(
            event,
            {
                "instance_id": inst.id,
                "chore_id": inst.chore_id,
                "member_id": inst.member_id,
                "points": inst.points_awarded,
            },
        )


async def _broadcast_updated(ws: WSManager, inst: ChoreInstance) -> None:
    await ws.broadcast(
        {
            "type": EVT_INSTANCE_UPDATED,
            "instance_id": inst.id,
            "member_id": inst.member_id,
            "state": inst.state.value,
        }
    )


# ─── state transitions ────────────────────────────────────────────────────


@_instance_router.post("/{instance_id}/complete", response_model=InstanceRead)
async def complete(
    instance_id: int,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    week_starts_on: str = Depends(get_week_starts_on),
    tz: str = Depends(get_effective_timezone),
    household_id: str | None = Depends(get_current_household_id),
) -> InstanceRead:
    inst = await complete_instance(
        session, instance_id, actor=user, household_id=household_id
    )
    await _finalize_action(
        session, inst, week_starts_on=week_starts_on, tz=tz, household_id=household_id
    )
    event = EVENT_COMPLETED if inst.state is InstanceState.DONE else None
    _notify_bridge(bridge, inst, event=event)
    await _broadcast_updated(ws, inst)
    return InstanceRead.model_validate(inst)


@_instance_router.post("/{instance_id}/undo", response_model=InstanceRead)
async def undo(
    instance_id: int,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    week_starts_on: str = Depends(get_week_starts_on),
    tz: str = Depends(get_effective_timezone),
    household_id: str | None = Depends(get_current_household_id),
) -> InstanceRead:
    inst = await undo_complete(session, instance_id, actor=user, household_id=household_id)
    await _finalize_action(
        session, inst, week_starts_on=week_starts_on, tz=tz, household_id=household_id
    )
    _notify_bridge(bridge, inst)
    await _broadcast_updated(ws, inst)
    return InstanceRead.model_validate(inst)


@_instance_router.post("/{instance_id}/approve", response_model=InstanceRead)
async def approve(
    instance_id: int,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    week_starts_on: str = Depends(get_week_starts_on),
    tz: str = Depends(get_effective_timezone),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> InstanceRead:
    inst = await approve_instance(
        session, instance_id, actor=user, household_id=household_id
    )
    await _finalize_action(
        session, inst, week_starts_on=week_starts_on, tz=tz, household_id=household_id
    )
    _notify_bridge(bridge, inst, event=EVENT_APPROVED)
    await _broadcast_updated(ws, inst)
    return InstanceRead.model_validate(inst)


@_instance_router.post("/{instance_id}/reject", response_model=InstanceRead)
async def reject(
    instance_id: int,
    body: RejectRequest = RejectRequest(),
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    week_starts_on: str = Depends(get_week_starts_on),
    tz: str = Depends(get_effective_timezone),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> InstanceRead:
    inst = await reject_instance(
        session, instance_id, actor=user, reason=body.reason, household_id=household_id
    )
    await _finalize_action(
        session, inst, week_starts_on=week_starts_on, tz=tz, household_id=household_id
    )
    _notify_bridge(bridge, inst)
    await _broadcast_updated(ws, inst)
    return InstanceRead.model_validate(inst)


@_instance_router.post("/{instance_id}/skip", response_model=InstanceRead)
async def skip(
    instance_id: int,
    body: RejectRequest = RejectRequest(),
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    week_starts_on: str = Depends(get_week_starts_on),
    tz: str = Depends(get_effective_timezone),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> InstanceRead:
    inst = await skip_instance(
        session, instance_id, actor=user, reason=body.reason, household_id=household_id
    )
    await _finalize_action(
        session, inst, week_starts_on=week_starts_on, tz=tz, household_id=household_id
    )
    _notify_bridge(bridge, inst)
    await _broadcast_updated(ws, inst)
    return InstanceRead.model_validate(inst)


# ─── points adjustment ────────────────────────────────────────────────────

_members_router = APIRouter(prefix="/members")


@_members_router.post("/{member_id}/points/adjust", response_model=MemberStatsRead)
async def adjust_points(
    member_id: int,
    body: AdjustPointsRequest,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> MemberStatsRead:
    stats = await adjust_member_points(
        session,
        member_id,
        actor=user,
        delta=body.delta,
        reason=body.reason,
        household_id=household_id,
    )
    await session.commit()
    bridge.notify_member_dirty(member_id)
    await ws.broadcast({"type": "member_updated", "member_id": member_id})
    return MemberStatsRead(
        points_total=stats.points_total,
        points_this_week=stats.points_this_week,
        week_anchor=stats.week_anchor,
        streak=stats.streak,
        last_all_done_date=stats.last_all_done_date,
    )


# ─── today aggregate view ─────────────────────────────────────────────────

_today_router = APIRouter()


def _today_window_utc(today: date_type, tz: str) -> tuple[datetime, datetime]:
    """Return (start, end) UTC bounds for "today" in `tz`.

    Start = local 00:00 today, end = local 00:00 tomorrow. Both are
    tz-aware UTC. Used to scope the calendar fetch so an event at
    11pm local (UTC + 5h) shows up as today, not tomorrow.
    """
    zone = ZoneInfo(tz)
    start_local = datetime.combine(today, time_type.min, tzinfo=zone)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


async def _shared_calendar_ids(
    session: AsyncSession, household_id: str | None
) -> list[str]:
    """Fetch the household's shared calendar entity ids. Returns
    empty when no row exists (fresh installs)."""
    if household_id is None:
        q = select(HouseholdSettings).where(
            HouseholdSettings.household_id.is_(None)
        )
    else:
        q = select(HouseholdSettings).where(
            HouseholdSettings.household_id == household_id
        )
    row = (await session.execute(q)).scalar_one_or_none()
    return list(row.shared_calendar_entity_ids or []) if row else []


def _calendar_event_to_read(event: CalendarEvent) -> CalendarEventRead:
    return CalendarEventRead.model_validate(event, from_attributes=True)


def _per_member_unreachable(
    member_calendar_map: dict[int, list[str]],
    unreachable: list[str],
) -> dict[int, list[str]]:
    """Project the global unreachable list down per-member so the UI
    can show a per-tile error state. A member is "affected" by an
    unreachable entity only if it appears in their mapping."""
    if not unreachable:
        return {mid: [] for mid in member_calendar_map}
    unreachable_set = set(unreachable)
    return {
        mid: [eid for eid in entity_ids if eid in unreachable_set]
        for mid, entity_ids in member_calendar_map.items()
    }


@_today_router.get("/today", response_model=TodayView)
async def today_view(
    tz: str = Depends(get_effective_timezone),
    session: AsyncSession = Depends(get_session),
    provider: CalendarProvider = Depends(get_calendar_provider),
    cache: CalendarCache = Depends(get_calendar_cache),
    household_id: str | None = Depends(get_current_household_id),
) -> TodayView:
    today = local_today(tz)

    member_result = await session.execute(
        select(Member)
        .where(scoped(Member.household_id, household_id))
        .options(selectinload(Member.stats))
        .order_by(Member.name)
    )
    members = list(member_result.scalars().all())
    if not members:
        return TodayView(date=today, members=[])

    inst_result = await session.execute(
        select(ChoreInstance, Chore)
        .join(Chore, Chore.id == ChoreInstance.chore_id)
        .where(ChoreInstance.date == today)
        .where(scoped(ChoreInstance.household_id, household_id))
        .order_by(Chore.name)
    )
    rows = inst_result.all()
    by_member: dict[int, list[tuple[ChoreInstance, Chore]]] = {}
    for inst, chore in rows:
        by_member.setdefault(inst.member_id, []).append((inst, chore))

    # ─── calendar fetch (DECISIONS §14) ────────────────────────────────
    # Single batched provider call for all entity ids the household
    # cares about today. Then `partition_by_member` shears the
    # event list per member, with shared calendars appearing under
    # every member that lists them. Failures degrade gracefully:
    # `calendar_events` ends up empty for that member; `unreachable`
    # propagates so the UI can render a per-tile hint.
    shared_ids = await _shared_calendar_ids(session, household_id)
    member_calendar_map: dict[int, list[str]] = {
        m.id: list(m.calendar_entity_ids or []) + shared_ids for m in members
    }
    all_entity_ids: list[str] = []
    seen_ids: set[str] = set()
    for ids in member_calendar_map.values():
        for eid in ids:
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            all_entity_ids.append(eid)

    events_by_member: dict[int, list[CalendarEvent]] = {m.id: [] for m in members}
    unreachable_by_member: dict[int, list[str]] = {m.id: [] for m in members}
    if all_entity_ids:
        try:
            from_dt, to_dt = _today_window_utc(today, tz)
            window = await get_events_for_window(
                provider, cache, all_entity_ids, from_dt, to_dt
            )
            now_utc = datetime.now(UTC)
            visible = hide_past(window.events, now=now_utc)
            partitioned = partition_by_member(visible, member_calendar_map)
            events_by_member.update(partitioned)
            unreachable_by_member = _per_member_unreachable(
                member_calendar_map, list(window.unreachable)
            )
        except Exception:
            # Calendar fetch is best-effort — chores must always render
            # even if HA is down. Log and continue with empty lists.
            log.exception("today_view calendar fetch failed; serving without events")

    today_members: list[TodayMember] = []
    for member in members:
        entries = by_member.get(member.id, [])
        done = sum(
            1
            for inst, _ in entries
            if inst.state
            in {
                InstanceState.DONE,
                InstanceState.DONE_UNAPPROVED,
                InstanceState.SKIPPED,
            }
        )
        progress = int((done / len(entries)) * 100) if entries else 0

        stats_read = MemberStatsRead(
            points_total=member.stats.points_total if member.stats else 0,
            points_this_week=member.stats.points_this_week if member.stats else 0,
            week_anchor=member.stats.week_anchor if member.stats else None,
            streak=member.stats.streak if member.stats else 0,
            last_all_done_date=member.stats.last_all_done_date if member.stats else None,
        )
        today_members.append(
            TodayMember(
                id=member.id,
                slug=member.slug,
                name=member.name,
                color=member.color,
                avatar=member.avatar,
                display_mode=member.display_mode,
                requires_approval=member.requires_approval,
                stats=stats_read,
                today_progress_pct=progress,
                instances=[
                    TodayInstance(
                        id=inst.id,
                        chore_id=chore.id,
                        chore_name=chore.name,
                        chore_icon=chore.icon,
                        points=chore.points,
                        state=inst.state,
                        time_window_start=chore.time_window_start,
                        time_window_end=chore.time_window_end,
                    )
                    for inst, chore in entries
                ],
                calendar_events=[
                    _calendar_event_to_read(e)
                    for e in events_by_member.get(member.id, [])
                ],
                calendar_unreachable=unreachable_by_member.get(member.id, []),
            )
        )
    return TodayView(date=today, members=today_members)


router.include_router(_instance_router)
router.include_router(_members_router)
router.include_router(_today_router)
