"""Chore-suggestions CRUD + starter-library reset.

The parent UI calls these "suggestions"; the code layer says
"chore_template" everywhere. See DECISIONS §13.

Routes:

  GET    /api/suggestions          list with filters (category/age/source/q)
  GET    /api/suggestions/{id}     single
  POST   /api/suggestions          create custom template
  PATCH  /api/suggestions/{id}     update (starter: name immutable)
  DELETE /api/suggestions/{id}     delete (starter -> insert suppression)
  POST   /api/suggestions/reset    clear suppression + reseed

All routes require parent role.

Dedup invariant: `(household_id, name_normalized)` uniqueness is
enforced at the application layer (SELECT first, then INSERT) because
the SQL UNIQUE constraint is a no-op for NULL household_id (single-tenant
addon mode) — see ChoreTemplate's docstring for the SQLite gotcha.
On conflict, POST and PATCH return 409 with `existing_id` so the
frontend can offer to use the existing template instead.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_api.deps import (
    get_current_household_id,
    get_session,
    require_parent,
)
from family_chores_api.errors import ConflictError, NotFoundError
from family_chores_api.schemas import (
    SuggestionCreate,
    SuggestionRead,
    SuggestionResetResult,
    SuggestionUpdate,
    validate_recurrence_config,
)
from family_chores_api.security import ParentClaim
from family_chores_api.services.starter_seeding import seed_starter_library
from family_chores_core.naming import normalize_chore_name
from family_chores_db.models import ChoreTemplate, HouseholdStarterSuppression
from family_chores_db.scoped import scoped

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


# ─── helpers ──────────────────────────────────────────────────────────────


async def _load_template(
    session: AsyncSession, template_id: str, household_id: str | None
) -> ChoreTemplate:
    result = await session.execute(
        select(ChoreTemplate).where(
            ChoreTemplate.id == template_id,
            scoped(ChoreTemplate.household_id, household_id),
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundError(f"suggestion id {template_id} not found")
    return template


async def _find_by_normalized_name(
    session: AsyncSession,
    name_normalized: str,
    household_id: str | None,
    *,
    exclude_id: str | None = None,
) -> ChoreTemplate | None:
    """Return the template (if any) with matching normalized name in this
    household. `exclude_id` lets PATCH skip the row being edited."""
    stmt = select(ChoreTemplate).where(
        scoped(ChoreTemplate.household_id, household_id),
        ChoreTemplate.name_normalized == name_normalized,
    )
    if exclude_id is not None:
        stmt = stmt.where(ChoreTemplate.id != exclude_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _conflict_with_existing_id(
    request: Request, detail: str, existing_id: str
) -> JSONResponse:
    """Return a 409 envelope with an extra `existing_id` field.

    The standard error envelope is `{error, detail, request_id}` (set by
    `app.py`'s exception handlers). For the dedup-conflict case the
    frontend needs to know which template already covers this name so it
    can offer "use existing instead" — we extend the envelope in this one
    case rather than encoding the id in the detail string.
    """
    rid = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=409,
        content={
            "error": "conflict",
            "detail": detail,
            "existing_id": existing_id,
            "request_id": rid,
        },
        headers={"X-Request-ID": rid},
    )


# ─── list / get ───────────────────────────────────────────────────────────


@router.get("", response_model=list[SuggestionRead])
async def list_suggestions(
    category: str | None = None,
    age: int | None = None,
    source: str = "all",
    q: str | None = None,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> list[SuggestionRead]:
    if source not in ("all", "starter", "custom"):
        raise ConflictError(
            f"source must be one of 'all', 'starter', 'custom' (got {source!r})"
        )

    stmt = select(ChoreTemplate).where(scoped(ChoreTemplate.household_id, household_id))
    if category is not None:
        stmt = stmt.where(ChoreTemplate.category == category)
    if source in ("starter", "custom"):
        stmt = stmt.where(ChoreTemplate.source == source)
    if age is not None:
        # Match if `age` falls within [age_min, age_max], with NULL bounds
        # treated as open-ended in that direction. NULL/NULL = always matches.
        stmt = stmt.where(
            or_(ChoreTemplate.age_min.is_(None), ChoreTemplate.age_min <= age),
            or_(ChoreTemplate.age_max.is_(None), ChoreTemplate.age_max >= age),
        )
    if q is not None and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(ChoreTemplate.name.ilike(like))
    stmt = stmt.order_by(ChoreTemplate.category, ChoreTemplate.name)

    result = await session.execute(stmt)
    return [SuggestionRead.model_validate(t) for t in result.scalars().all()]


@router.get("/{template_id}", response_model=SuggestionRead)
async def get_suggestion(
    template_id: str,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> SuggestionRead:
    template = await _load_template(session, template_id, household_id)
    return SuggestionRead.model_validate(template)


# ─── create / update / delete ─────────────────────────────────────────────


@router.post("", response_model=SuggestionRead, status_code=201)
async def create_suggestion(
    body: SuggestionCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> SuggestionRead | JSONResponse:
    name_normalized = normalize_chore_name(body.name)
    if not name_normalized:
        # Empty after normalization — `normalize_chore_name` is permissive
        # and the model layer requires `name` to be non-empty, but a name
        # of "..." normalizes to "" which we still want to reject.
        raise ConflictError("name cannot be empty after normalization")

    existing = await _find_by_normalized_name(session, name_normalized, household_id)
    if existing is not None:
        return _conflict_with_existing_id(
            request,
            f"a suggestion with this name already exists (id={existing.id})",
            existing.id,
        )

    template = ChoreTemplate(
        id=str(uuid.uuid4()),
        household_id=household_id,
        name=body.name,
        name_normalized=name_normalized,
        icon=body.icon,
        category=body.category,
        age_min=body.age_min,
        age_max=body.age_max,
        points_suggested=body.points_suggested,
        default_recurrence_type=body.default_recurrence_type,
        default_recurrence_config=body.default_recurrence_config,
        description=body.description,
        source="custom",
        starter_key=None,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return SuggestionRead.model_validate(template)


@router.patch("/{template_id}", response_model=SuggestionRead)
async def update_suggestion(
    template_id: str,
    body: SuggestionUpdate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> SuggestionRead | JSONResponse:
    template = await _load_template(session, template_id, household_id)
    updates = body.model_dump(exclude_unset=True)

    if template.source == "starter" and "name" in updates:
        # Starter name is immutable per §1.2 — keeps the dedup story
        # intact (starter_key plus name_normalized would diverge if a
        # parent renamed a starter, breaking subsequent dedup attempts).
        raise ConflictError("starter suggestions cannot be renamed")

    if "name" in updates:
        new_normalized = normalize_chore_name(updates["name"])
        if not new_normalized:
            raise ConflictError("name cannot be empty after normalization")
        dup = await _find_by_normalized_name(
            session, new_normalized, household_id, exclude_id=template.id
        )
        if dup is not None:
            return _conflict_with_existing_id(
                request,
                f"a suggestion with this name already exists (id={dup.id})",
                dup.id,
            )
        updates["name_normalized"] = new_normalized

    if (
        "default_recurrence_type" in updates
        or "default_recurrence_config" in updates
    ):
        target_type = updates.get(
            "default_recurrence_type", template.default_recurrence_type
        )
        target_cfg = updates.get(
            "default_recurrence_config", template.default_recurrence_config
        )
        try:
            updates["default_recurrence_config"] = validate_recurrence_config(
                target_type, target_cfg or {}
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    for field_name, value in updates.items():
        setattr(template, field_name, value)
    await session.commit()
    await session.refresh(template)
    return SuggestionRead.model_validate(template)


@router.delete("/{template_id}")
async def delete_suggestion(
    template_id: str,
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> Response:
    template = await _load_template(session, template_id, household_id)

    if template.source == "starter" and template.starter_key is not None:
        # Soft delete: hard-delete the row + remember the starter_key in
        # suppression so the next seeding run skips it. Skip-if-already-
        # suppressed because the SQLite NULL gotcha means the composite
        # PK doesn't enforce uniqueness in single-tenant mode.
        existing = await session.execute(
            select(HouseholdStarterSuppression).where(
                scoped(HouseholdStarterSuppression.household_id, household_id),
                HouseholdStarterSuppression.starter_key == template.starter_key,
            )
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                HouseholdStarterSuppression(
                    household_id=household_id,
                    starter_key=template.starter_key,
                )
            )

    await session.delete(template)
    await session.commit()
    return Response(status_code=204)


# ─── reset ────────────────────────────────────────────────────────────────


@router.post("/reset", response_model=SuggestionResetResult)
async def reset_suggestions(
    session: AsyncSession = Depends(get_session),
    household_id: str | None = Depends(get_current_household_id),
    _parent: ParentClaim = Depends(require_parent),
) -> SuggestionResetResult:
    """Clear suppression rows for this household, then re-seed.

    Restores any starter templates the parent had previously deleted.
    Custom templates are not affected.
    """
    # Count first via SELECT, then bulk DELETE. Two reasons:
    #   1. `session.delete(obj)` per-row fails with `FlushError: Can't
    #      delete using NULL for primary key` when household_id is NULL
    #      (single-tenant addon) — the implied WHERE compares NULL=NULL.
    #      A SQL DELETE through `scoped()` emits IS NULL and works.
    #   2. CursorResult.rowcount is correct at runtime but the
    #      Result[Any] type doesn't carry it, so we'd need a cast.
    #      Counting via SELECT first is type-clean and matches the
    #      seeder's pattern in starter_seeding.py.
    existing_keys = (
        await session.execute(
            select(HouseholdStarterSuppression.starter_key).where(
                scoped(HouseholdStarterSuppression.household_id, household_id),
            )
        )
    ).scalars().all()
    suppressions_cleared = len(existing_keys)

    await session.execute(
        delete(HouseholdStarterSuppression).where(
            scoped(HouseholdStarterSuppression.household_id, household_id),
        )
    )
    # Flush so the seeder's SELECT against suppression sees the deletions
    # (the seeder reads in the same transaction below).
    await session.flush()

    seed = await seed_starter_library(session, household_id=household_id)
    await session.commit()

    return SuggestionResetResult(
        suppressions_cleared=suppressions_cleared,
        seeded=seed.seeded,
        library_version=seed.library_version,
    )
