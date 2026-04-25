"""Seed the bundled starter library into a household's chore_template rows.

Idempotent — re-running this function for the same household is a no-op
on already-seeded entries. Suppression-aware — starter_keys present in
`household_starter_suppression` for the household are skipped so a
parent's deletions survive add-on restarts.

Library version upgrade policy (DECISIONS §13 §4.3):

  - **New entries** (a new `starter_key` shows up in v2 of the library)
    seed into every existing household on the next call.
  - **Existing entries are NEVER updated.** If v2 changes `make_bed`
    from 2 points to 3, households with the v1 2-point row keep theirs.
    This is non-negotiable — it's how parent customizations survive
    upgrades.
  - **Removed entries** (a key in v1 but not v2) stay in user DBs. We
    never auto-remove.

The dedup invariant relies on the application-layer "skip if exists"
check rather than the SQL UNIQUE constraint — see ChoreTemplate's
docstring for the SQLite NULL-distinct gotcha that makes the constraint
non-load-bearing in single-tenant addon mode.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_core.naming import normalize_chore_name
from family_chores_core.starter_library import (
    StarterLibrary,
    library_recurrence_to_engine,
    load_starter_library,
)
from family_chores_db.models import ChoreTemplate, HouseholdStarterSuppression
from family_chores_db.scoped import scoped

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Outcome of one seeding pass — returned for tests / lifespan logging."""

    household_id: str | None
    library_version: int
    seeded: int
    skipped_existing: int
    skipped_suppressed: int


async def seed_starter_library(
    session: AsyncSession,
    *,
    household_id: str | None,
    library: StarterLibrary | None = None,
) -> SeedResult:
    """Seed (or top up) the bundled starter library for one household.

    Adds new `ChoreTemplate` rows for any library entry not already
    present (by `starter_key`) and not in the household's suppression
    list. Caller is responsible for committing the session.

    Production callers omit `library` and the bundled JSON is loaded.
    Tests pass a synthetic `StarterLibrary` to exercise specific paths.
    """
    lib = library if library is not None else load_starter_library()

    # Bulk-fetch existing starter_keys for this household — one query
    # rather than 46 SELECTs.
    existing_stmt = select(ChoreTemplate.starter_key).where(
        scoped(ChoreTemplate.household_id, household_id),
        ChoreTemplate.source == "starter",
        ChoreTemplate.starter_key.is_not(None),
    )
    existing_keys: set[str] = {
        row[0] for row in (await session.execute(existing_stmt)).all()
    }

    suppressed_stmt = select(HouseholdStarterSuppression.starter_key).where(
        scoped(HouseholdStarterSuppression.household_id, household_id)
    )
    suppressed_keys: set[str] = {
        row[0] for row in (await session.execute(suppressed_stmt)).all()
    }

    seeded = 0
    skipped_existing = 0
    skipped_suppressed = 0

    for entry in lib.chores:
        if entry.key in existing_keys:
            skipped_existing += 1
            continue
        if entry.key in suppressed_keys:
            skipped_suppressed += 1
            continue
        rt, cfg = library_recurrence_to_engine(entry.default_recurrence)
        session.add(
            ChoreTemplate(
                id=str(uuid.uuid4()),
                household_id=household_id,
                name=entry.name,
                name_normalized=normalize_chore_name(entry.name),
                icon=entry.icon,
                category=entry.category,
                age_min=entry.age_min,
                age_max=entry.age_max,
                points_suggested=entry.points_suggested,
                default_recurrence_type=rt,
                default_recurrence_config=cfg,
                description=entry.description,
                source="starter",
                starter_key=entry.key,
            )
        )
        seeded += 1

    result = SeedResult(
        household_id=household_id,
        library_version=lib.version,
        seeded=seeded,
        skipped_existing=skipped_existing,
        skipped_suppressed=skipped_suppressed,
    )

    log.info(
        "starter library seed: household=%s library_version=%d "
        "seeded=%d skipped_existing=%d skipped_suppressed=%d",
        household_id or "<single-tenant>",
        lib.version,
        seeded,
        skipped_existing,
        skipped_suppressed,
    )

    return result
