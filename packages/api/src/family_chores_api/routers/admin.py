"""Admin endpoints — behind parent-only guard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
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
from family_chores_api.events import EVT_STATS_REBUILT, WSManager
from family_chores_api.schemas import (
    ActivityLogEntry,
    ActivityLogPage,
)
from family_chores_api.services.stats_service import recompute_stats_for_member
from family_chores_core.time import local_today
from family_chores_db.models import ActivityLog, Member
from family_chores_db.scoped import scoped

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_parent)])


@router.post("/rebuild-stats")
async def rebuild_stats(
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
    bridge: BridgeProtocol = Depends(get_bridge),
    tz: str = Depends(get_effective_timezone),
    week_starts_on: str = Depends(get_week_starts_on),
    household_id: str | None = Depends(get_current_household_id),
) -> dict[str, int]:
    today = local_today(tz)
    ids = list(
        (
            await session.execute(
                select(Member.id).where(scoped(Member.household_id, household_id))
            )
        )
        .scalars()
        .all()
    )
    for mid in ids:
        await recompute_stats_for_member(
            session,
            mid,
            today=today,
            week_starts_on=week_starts_on,
            household_id=household_id,
        )
    session.add(
        ActivityLog(
            actor=user,
            action="stats_rebuilt",
            payload={"members": len(ids)},
            household_id=household_id,
        )
    )
    await session.commit()
    for mid in ids:
        bridge.notify_member_dirty(mid)
    bridge.notify_approvals_dirty()
    await ws.broadcast({"type": EVT_STATS_REBUILT, "members": len(ids)})
    return {"members_updated": len(ids)}


@router.get("/activity", response_model=ActivityLogPage)
async def list_activity(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> ActivityLogPage:
    count_stmt = (
        select(func.count())
        .select_from(ActivityLog)
        .where(scoped(ActivityLog.household_id, household_id))
    )
    stmt = (
        select(ActivityLog)
        .where(scoped(ActivityLog.household_id, household_id))
        .order_by(ActivityLog.ts.desc(), ActivityLog.id.desc())
    )
    if action is not None:
        count_stmt = count_stmt.where(ActivityLog.action == action)
        stmt = stmt.where(ActivityLog.action == action)

    total = int((await session.execute(count_stmt)).scalar_one())
    rows = list(
        (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()
    )
    return ActivityLogPage(
        entries=[ActivityLogEntry.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
