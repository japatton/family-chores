"""Tenant-scope SQLAlchemy filter helper.

Every service-layer query that reads from a tenant-scoped table (per
DECISIONS §11 step 8 — `members`, `chores`, `chore_assignments`,
`chore_instances`, `member_stats`, `activity_log`, `app_config`) goes
through `scoped(col, household_id)` to attach the right WHERE clause.

Why a helper instead of inline `col == value`:

  - SQLite (and ANSI SQL) treat `NULL = NULL` as **false**, so the naive
    `Member.household_id == None` would match zero rows in single-
    tenant add-on mode (where every row's `household_id` is NULL). The
    helper emits `IS NULL` for that case via SQLAlchemy's `col.is_(None)`.
  - Centralising the predicate means the day we want to add a
    "shared-with-other-household" feature, every query gets the upgrade
    by editing one function instead of grepping for `household_id ==`.

Usage in a service:

    stmt = select(Member).where(scoped(Member.household_id, household_id))

Where `household_id: str | None` is the dep-injected value from
`family_chores_api.deps.tenant.get_current_household_id`. The add-on
always passes `None`; the (future) SaaS passes a real household uuid.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.sql.elements import ColumnElement


def scoped(col: Any, value: str | None) -> ColumnElement[bool]:
    """Return the right WHERE clause for the given tenant-scope value.

    `col` is a SQLAlchemy column — typically `Member.household_id` etc.
    `value` is a household UUID string in multi-tenant mode, or `None`
    in single-tenant add-on mode.

    Typed loose (`Any`) on `col` because instrumented attributes from
    SQLAlchemy mapped classes don't have a single nice type alias.
    """
    if value is None:
        return col.is_(None)
    return col == value
