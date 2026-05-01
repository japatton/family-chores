"""Calendar endpoints (DECISIONS §14).

Two endpoints:

  - `GET /api/calendar/events` — fetch events for a window. `from` and
    `to` are required ISO 8601 datetimes. `member_id` (optional)
    scopes to one member's calendars + the household-shared list;
    omitted means "all calendars (per-member + shared)" which is what
    the parent's monthly view consumes. The response includes
    `unreachable: list[str]` so the UI can render a per-tile error
    state without losing the calendars that did succeed.

  - `POST /api/calendar/refresh` — drop the cache so the next read
    re-fetches from the provider. Parent-only; backs the parent's
    explicit refresh button on the monthly view.

Past-event filtering (DECISIONS §14 Q7) is the caller's concern; the
endpoint returns events as-is in the requested window so the monthly
view can still render past days.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from family_chores_api.deps import (
    get_calendar_cache,
    get_calendar_provider,
    get_current_household_id,
    get_session,
    require_parent,
)
from family_chores_api.errors import NotFoundError, ValidationError
from family_chores_api.schemas import (
    CalendarEventRead,
    CalendarRefreshResponse,
    CalendarWindowRead,
)
from family_chores_api.security import ParentClaim
from family_chores_api.services.calendar import (
    CalendarCache,
    CalendarProvider,
    get_events_for_window,
)
from family_chores_db.models import HouseholdSettings, Member
from family_chores_db.scoped import scoped

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


async def _resolve_entity_ids(
    session: AsyncSession,
    household_id: str | None,
    member_id: int | None,
) -> list[str]:
    """Build the entity_id list for a calendar query.

    - `member_id` set → that member's calendar_entity_ids + the
      household's shared list.
    - `member_id` None → every member's calendars + the shared list,
      de-duped (parent's monthly-view consumer).

    De-dupe preserves first-seen order so the SPA's color-coding stays
    stable across refreshes.
    """
    if household_id is None:
        settings_q = select(HouseholdSettings).where(
            HouseholdSettings.household_id.is_(None)
        )
    else:
        settings_q = select(HouseholdSettings).where(
            HouseholdSettings.household_id == household_id
        )
    settings_row = (await session.execute(settings_q)).scalar_one_or_none()
    shared = list(settings_row.shared_calendar_entity_ids or []) if settings_row else []

    if member_id is not None:
        member = (
            await session.execute(
                select(Member)
                .where(
                    Member.id == member_id,
                    scoped(Member.household_id, household_id),
                )
                .options(selectinload(Member.stats))
            )
        ).scalar_one_or_none()
        if member is None:
            raise NotFoundError(f"member id {member_id} not found")
        per_member = list(member.calendar_entity_ids or [])
        seen: set[str] = set()
        out: list[str] = []
        for eid in per_member + shared:
            if eid in seen:
                continue
            seen.add(eid)
            out.append(eid)
        return out

    # All members + shared.
    rows = (
        await session.execute(
            select(Member.calendar_entity_ids).where(
                scoped(Member.household_id, household_id)
            )
        )
    ).all()
    seen2: set[str] = set()
    out2: list[str] = []
    for (entity_ids,) in rows:
        for eid in list(entity_ids or []):
            if eid in seen2:
                continue
            seen2.add(eid)
            out2.append(eid)
    for eid in shared:
        if eid in seen2:
            continue
        seen2.add(eid)
        out2.append(eid)
    return out2


@router.get("/events", response_model=CalendarWindowRead)
async def list_events(
    from_dt: datetime = Query(..., alias="from"),
    to_dt: datetime = Query(..., alias="to"),
    member_id: int | None = Query(None, ge=1),
    session: AsyncSession = Depends(get_session),
    provider: CalendarProvider = Depends(get_calendar_provider),
    cache: CalendarCache = Depends(get_calendar_cache),
    household_id: str | None = Depends(get_current_household_id),
) -> CalendarWindowRead:
    if to_dt < from_dt:
        raise ValidationError("'to' must be on or after 'from'")

    entity_ids = await _resolve_entity_ids(session, household_id, member_id)
    if not entity_ids:
        # No mapping yet → empty window, no provider call. Distinct
        # from "asked the provider, got nothing" which would still
        # report unreachable. UI renders the empty state.
        return CalendarWindowRead(events=[], unreachable=[])

    window = await get_events_for_window(
        provider, cache, entity_ids, from_dt, to_dt
    )
    return CalendarWindowRead(
        events=[
            CalendarEventRead.model_validate(e, from_attributes=True)
            for e in window.events
        ],
        unreachable=list(window.unreachable),
    )


@router.post("/refresh", response_model=CalendarRefreshResponse)
async def refresh_cache(
    cache: CalendarCache = Depends(get_calendar_cache),
    _parent: ParentClaim = Depends(require_parent),
) -> CalendarRefreshResponse:
    """Drop every cached `(entity_id, day)` cell. Parent-only — the
    kid view doesn't get to spam the provider."""
    dropped = await cache.invalidate()
    return CalendarRefreshResponse(invalidated=dropped)
