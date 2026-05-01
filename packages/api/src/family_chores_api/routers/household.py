"""Household-level settings endpoints (DECISIONS §14).

Single-row-per-household configuration that's cleaner as named columns
than as opaque JSON values in `app_config`. First column shipped:
`shared_calendar_entity_ids` for the calendar integration's family-
shared layer (events from these calendars appear on every member's
view).

Endpoints:

  - `GET /api/household/settings` — read current values. Open to any
    authenticated caller so the kid view can fetch the shared calendar
    list for rendering.
  - `PUT /api/household/settings` — partial update (None fields stay
    unchanged). Parent-only. Invalidates the calendar cache so the
    next read sees the new entity list immediately.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_api.deps import (
    get_calendar_cache,
    get_current_household_id,
    get_remote_user,
    get_session,
    require_parent,
)
from family_chores_api.schemas import (
    HouseholdSettingsRead,
    HouseholdSettingsUpdate,
)
from family_chores_api.security import ParentClaim
from family_chores_api.services.calendar import CalendarCache
from family_chores_db.models import ActivityLog, HouseholdSettings

router = APIRouter(prefix="/api/household", tags=["household"])


def _scoped_settings_query(household_id: str | None):  # type: ignore[no-untyped-def]
    """Build a `select(HouseholdSettings)` filtered by household_id.

    SQLAlchemy doesn't equate `==` and `IS NULL` — single-tenant
    (`household_id is None`) needs an explicit `.is_(None)` clause.
    Returns a `Select` ready to feed `session.execute`.
    """
    if household_id is None:
        return select(HouseholdSettings).where(
            HouseholdSettings.household_id.is_(None)
        )
    return select(HouseholdSettings).where(
        HouseholdSettings.household_id == household_id
    )


async def _load_or_create(
    session: AsyncSession, household_id: str | None
) -> HouseholdSettings:
    """Settings row is materialised on first read — no migration-time
    seeding needed. Single-row-per-household is enforced here (not by
    a UNIQUE constraint, which SQLite doesn't honour on NULL columns).
    """
    row = (
        await session.execute(_scoped_settings_query(household_id))
    ).scalar_one_or_none()
    if row is None:
        row = HouseholdSettings(
            household_id=household_id, shared_calendar_entity_ids=[]
        )
        session.add(row)
        await session.flush()
    return row


@router.get("/settings", response_model=HouseholdSettingsRead)
async def get_settings(
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
) -> HouseholdSettingsRead:
    # Read-only path uses get-or-default to avoid creating a row just
    # for a passive read. Mutate-on-PUT keeps writes explicit.
    settings = (
        await session.execute(_scoped_settings_query(household_id))
    ).scalar_one_or_none()
    if settings is None:
        return HouseholdSettingsRead(
            shared_calendar_entity_ids=[], updated_at=None
        )
    return HouseholdSettingsRead(
        shared_calendar_entity_ids=list(settings.shared_calendar_entity_ids or []),
        updated_at=settings.updated_at,
    )


@router.put("/settings", response_model=HouseholdSettingsRead)
async def update_settings(
    body: HouseholdSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    cache: CalendarCache = Depends(get_calendar_cache),
    user: str = Depends(get_remote_user),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> HouseholdSettingsRead:
    settings = await _load_or_create(session, household_id)

    changes: dict[str, object] = {}
    if body.shared_calendar_entity_ids is not None:
        old = list(settings.shared_calendar_entity_ids or [])
        new = list(body.shared_calendar_entity_ids)
        if old != new:
            settings.shared_calendar_entity_ids = new
            settings.updated_at = datetime.now(UTC)
            changes["shared_calendar_entity_ids"] = {"old": old, "new": new}

    if changes:
        session.add(
            ActivityLog(
                actor=user,
                action="household_settings_updated",
                payload={"changes": changes},
                household_id=household_id,
            )
        )
    await session.commit()

    if changes:
        # Calendar cache holds (entity_id, day) entries from BEFORE the
        # entity-list change; drop everything so the next read sees the
        # new entity set without stale data. Cheap (single-process,
        # in-memory) and matches the docstring's "cache-bust on config
        # mutation" contract.
        await cache.invalidate()

    return HouseholdSettingsRead(
        shared_calendar_entity_ids=list(settings.shared_calendar_entity_ids or []),
        updated_at=settings.updated_at,
    )
