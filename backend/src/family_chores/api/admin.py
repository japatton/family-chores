"""Admin endpoints — behind parent-only guard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores.api.deps import (
    get_options,
    get_remote_user,
    get_session,
    get_ws_manager,
    require_parent,
)
from family_chores.api.events import EVT_STATS_REBUILT, WSManager
from family_chores.api.schemas import (
    ActivityLogEntry,
    ActivityLogPage,
)
from family_chores.config import Options
from family_chores.core.time import local_today
from family_chores.db.models import ActivityLog, Member
from family_chores.services.stats_service import recompute_stats_for_member

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_parent)])


@router.post("/rebuild-stats")
async def rebuild_stats(
    opts: Options = Depends(get_options),
    session: AsyncSession = Depends(get_session),
    user: str = Depends(get_remote_user),
    ws: WSManager = Depends(get_ws_manager),
) -> dict[str, int]:
    today = local_today(opts.effective_timezone)
    ids = list((await session.execute(select(Member.id))).scalars().all())
    for mid in ids:
        await recompute_stats_for_member(
            session, mid, today=today, week_starts_on=opts.week_starts_on
        )
    session.add(ActivityLog(actor=user, action="stats_rebuilt", payload={"members": len(ids)}))
    await session.commit()
    await ws.broadcast({"type": EVT_STATS_REBUILT, "members": len(ids)})
    return {"members_updated": len(ids)}


@router.get("/activity", response_model=ActivityLogPage)
async def list_activity(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> ActivityLogPage:
    count_stmt = select(func.count()).select_from(ActivityLog)
    stmt = select(ActivityLog).order_by(ActivityLog.ts.desc(), ActivityLog.id.desc())
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
