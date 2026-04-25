"""Integration tests for starter library seeding (DECISIONS §13 step 4).

Covers the seeder's idempotency, suppression-awareness, and library-
version-upgrade contract. Uses real SQLite via the `async_session`
conftest fixture, not the bundled JSON — synthetic `StarterLibrary`
objects let each test target a specific path without depending on
the 46-entry production library.

Companion tests against the bundled JSON live in
`packages/core/tests/test_starter_library.py`.
"""

from __future__ import annotations

import pytest
from family_chores_api.services.starter_seeding import (
    SeedResult,
    seed_starter_library,
)
from family_chores_core.starter_library import (
    StarterLibrary,
    StarterLibraryEntry,
    load_starter_library,
)
from family_chores_db.models import ChoreTemplate, HouseholdStarterSuppression
from family_chores_db.scoped import scoped
from sqlalchemy import select

# ─── helpers ──────────────────────────────────────────────────────────────


def _entry(
    key: str,
    *,
    name: str | None = None,
    category: str = "bedroom",
    points: int = 2,
    recurrence: str = "daily",
) -> StarterLibraryEntry:
    return StarterLibraryEntry(
        key=key,
        name=name or key.replace("_", " ").title(),
        icon="mdi:test",
        category=category,
        age_min=4,
        age_max=None,
        points_suggested=points,
        default_recurrence=recurrence,
        description=f"description for {key}",
    )


def _library(*entries: StarterLibraryEntry, version: int = 1) -> StarterLibrary:
    return StarterLibrary(
        version=version,
        updated="2026-04-25",
        chores=tuple(entries),
    )


async def _all_templates(session) -> list[ChoreTemplate]:
    result = await session.execute(select(ChoreTemplate).order_by(ChoreTemplate.starter_key))
    return list(result.scalars().all())


# ─── happy paths ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_into_empty_db_creates_all_entries(async_session):
    """Production library — 46 starter rows in, all source='starter'."""
    result = await seed_starter_library(async_session, household_id=None)
    await async_session.commit()

    assert result.seeded == 46
    assert result.skipped_existing == 0
    assert result.skipped_suppressed == 0

    rows = await _all_templates(async_session)
    assert len(rows) == 46
    assert all(r.source == "starter" for r in rows)
    assert all(r.starter_key is not None for r in rows)
    assert all(r.household_id is None for r in rows)
    # name_normalized populated for every row
    assert all(r.name_normalized for r in rows)


@pytest.mark.asyncio
async def test_seed_twice_is_idempotent(async_session):
    """Re-running the seeder with identical state must not duplicate rows."""
    first = await seed_starter_library(async_session, household_id=None)
    await async_session.commit()
    second = await seed_starter_library(async_session, household_id=None)
    await async_session.commit()

    assert first.seeded == 46
    assert second.seeded == 0
    assert second.skipped_existing == 46
    assert second.skipped_suppressed == 0

    rows = await _all_templates(async_session)
    assert len(rows) == 46


@pytest.mark.asyncio
async def test_seed_uses_synthetic_library(async_session):
    """Tests pass `library=` to bypass the real JSON."""
    lib = _library(_entry("a"), _entry("b"), _entry("c"))
    result = await seed_starter_library(
        async_session, household_id=None, library=lib
    )
    await async_session.commit()

    assert result.seeded == 3
    rows = await _all_templates(async_session)
    assert {r.starter_key for r in rows} == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_seed_translates_weekly_to_specific_days(async_session):
    """library_recurrence_to_engine flow — weekly entries land as
    SPECIFIC_DAYS with Saturday default."""
    from family_chores_core.enums import RecurrenceType

    lib = _library(_entry("weekly_thing", recurrence="weekly"))
    await seed_starter_library(async_session, household_id=None, library=lib)
    await async_session.commit()

    row = (await _all_templates(async_session))[0]
    assert row.default_recurrence_type is RecurrenceType.SPECIFIC_DAYS
    assert row.default_recurrence_config == {"days": [6]}


# ─── suppression ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_suppressed_starter_key_is_skipped(async_session):
    """A row in household_starter_suppression for `make_bed` means the
    seeder must not re-insert that template on subsequent runs."""
    async_session.add(
        HouseholdStarterSuppression(household_id=None, starter_key="make_bed")
    )
    await async_session.commit()

    lib = _library(_entry("make_bed"), _entry("brush_teeth"))
    result = await seed_starter_library(
        async_session, household_id=None, library=lib
    )
    await async_session.commit()

    assert result.seeded == 1
    assert result.skipped_suppressed == 1
    rows = await _all_templates(async_session)
    assert {r.starter_key for r in rows} == {"brush_teeth"}


@pytest.mark.asyncio
async def test_suppression_only_blocks_for_matching_household(async_session):
    """Suppression for household A must not affect household B's seeding."""
    async_session.add(
        HouseholdStarterSuppression(
            household_id="household-a", starter_key="make_bed"
        )
    )
    await async_session.commit()

    lib = _library(_entry("make_bed"))

    res_a = await seed_starter_library(
        async_session, household_id="household-a", library=lib
    )
    res_b = await seed_starter_library(
        async_session, household_id="household-b", library=lib
    )
    await async_session.commit()

    assert res_a.seeded == 0
    assert res_a.skipped_suppressed == 1
    assert res_b.seeded == 1
    assert res_b.skipped_suppressed == 0


# ─── library upgrade behaviour (DECISIONS §13 §4.3) ───────────────────────


@pytest.mark.asyncio
async def test_user_modified_starter_template_is_not_overwritten(async_session):
    """The whole point of "skip if exists": parent edits a starter's
    points; next seeder run must not clobber the edit."""
    lib = _library(_entry("make_bed", points=2))
    await seed_starter_library(async_session, household_id=None, library=lib)
    await async_session.commit()

    # Parent bumps points from 2 to 5.
    row = (await _all_templates(async_session))[0]
    row.points_suggested = 5
    await async_session.commit()

    # Re-seed with the same library version — parent customization survives.
    result = await seed_starter_library(
        async_session, household_id=None, library=lib
    )
    await async_session.commit()

    assert result.seeded == 0
    assert result.skipped_existing == 1
    refreshed = (await _all_templates(async_session))[0]
    assert refreshed.points_suggested == 5, "parent edit was clobbered"


@pytest.mark.asyncio
async def test_v2_library_seeds_only_new_entries(async_session):
    """Simulated upgrade: v1 has 2 entries; v2 adds a third. Existing
    rows untouched, just the new entry seeded."""
    v1 = _library(_entry("a"), _entry("b"), version=1)
    await seed_starter_library(async_session, household_id=None, library=v1)
    await async_session.commit()

    v2 = _library(_entry("a"), _entry("b"), _entry("c", points=99), version=2)
    result = await seed_starter_library(
        async_session, household_id=None, library=v2
    )
    await async_session.commit()

    assert result.seeded == 1
    assert result.skipped_existing == 2
    rows = await _all_templates(async_session)
    assert {r.starter_key for r in rows} == {"a", "b", "c"}
    new_row = next(r for r in rows if r.starter_key == "c")
    assert new_row.points_suggested == 99


@pytest.mark.asyncio
async def test_v2_library_does_not_update_existing_entries(async_session):
    """If v2 changes `make_bed` from 2 points to 3, the existing
    household keeps its 2-point row untouched (DECISIONS §13 §4.3)."""
    v1 = _library(_entry("make_bed", points=2), version=1)
    await seed_starter_library(async_session, household_id=None, library=v1)
    await async_session.commit()

    v2 = _library(_entry("make_bed", points=3), version=2)
    result = await seed_starter_library(
        async_session, household_id=None, library=v2
    )
    await async_session.commit()

    assert result.seeded == 0
    assert result.skipped_existing == 1
    row = (await _all_templates(async_session))[0]
    assert row.points_suggested == 2, "v2 should not have updated existing row"


# ─── tenant isolation ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seeding_two_households_keeps_them_separate(async_session):
    """Each household gets its own copy. Templates for A invisible to B's
    seeder; both end up with the same set of starter_keys but different
    rows / IDs."""
    lib = _library(_entry("a"), _entry("b"))
    res_a = await seed_starter_library(
        async_session, household_id="household-a", library=lib
    )
    res_b = await seed_starter_library(
        async_session, household_id="household-b", library=lib
    )
    await async_session.commit()

    assert res_a.seeded == 2
    assert res_b.seeded == 2

    a_rows = (
        await async_session.execute(
            select(ChoreTemplate).where(
                scoped(ChoreTemplate.household_id, "household-a")
            )
        )
    ).scalars().all()
    b_rows = (
        await async_session.execute(
            select(ChoreTemplate).where(
                scoped(ChoreTemplate.household_id, "household-b")
            )
        )
    ).scalars().all()
    assert {r.starter_key for r in a_rows} == {"a", "b"}
    assert {r.starter_key for r in b_rows} == {"a", "b"}
    assert {r.id for r in a_rows}.isdisjoint({r.id for r in b_rows})


# ─── result shape ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_seed_result_carries_library_version_and_household(async_session):
    lib = _library(_entry("a"), version=42)
    result = await seed_starter_library(
        async_session, household_id="household-x", library=lib
    )
    await async_session.commit()

    assert result == SeedResult(
        household_id="household-x",
        library_version=42,
        seeded=1,
        skipped_existing=0,
        skipped_suppressed=0,
    )


@pytest.mark.asyncio
async def test_seed_loads_real_library_when_no_argument(async_session):
    """Default code path — no `library=` argument loads the bundled JSON."""
    real_lib = load_starter_library()
    result = await seed_starter_library(async_session, household_id=None)
    await async_session.commit()

    assert result.seeded == len(real_lib.chores)
    assert result.library_version == real_lib.version
