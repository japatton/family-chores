"""Domain enums shared across deployment targets.

These describe values that are part of the domain language — how a chore
recurs, what state an instance is in. They live in `family_chores_core`
(not in `family_chores_db.models`) so the `core` → `db` dependency arrow
stays one-way: `db.models` imports these to type its columns; `core`
modules import them to reason about domain transitions.

Stored on the wire as plain strings (`native_enum=False` in SQLAlchemy —
see DECISIONS §4 #22) so adding a value is a pure code change with no
schema migration required.

`DisplayMode` deliberately stays in `family_chores_db.models` — it's a
member-presentation preference, not domain logic, and it's only consumed
by the data and API layers.

Extracted here in Phase 2 step 2 of the monorepo refactor. Before the
extraction, `RecurrenceType` and `InstanceState` lived inside
`family_chores.db.models` and were imported back into `core` — a
package-level circular reference that the architecture rule forbids.
"""

from __future__ import annotations

import enum


class RecurrenceType(str, enum.Enum):
    DAILY = "daily"
    WEEKDAYS = "weekdays"
    WEEKENDS = "weekends"
    SPECIFIC_DAYS = "specific_days"
    EVERY_N_DAYS = "every_n_days"
    MONTHLY_ON_DATE = "monthly_on_date"
    ONCE = "once"


class InstanceState(str, enum.Enum):
    PENDING = "pending"
    DONE_UNAPPROVED = "done_unapproved"
    DONE = "done"
    SKIPPED = "skipped"
    MISSED = "missed"


class ChoreCategory(str, enum.Enum):
    """Canonical category set for chores and chore templates.

    Added in DECISIONS §13 alongside the chore-suggestions feature. Used to
    group templates in the Browse Suggestions panel and to validate the
    bundled starter library at load time. Extending this enum is a pure
    code change with no migration (categories are stored as plain strings
    on `chore_template.category`, see `RecurrenceType` for the same
    `native_enum=False` rationale).
    """

    BEDROOM = "bedroom"
    BATHROOM = "bathroom"
    KITCHEN = "kitchen"
    LAUNDRY = "laundry"
    PET_CARE = "pet_care"
    OUTDOOR = "outdoor"
    PERSONAL_CARE = "personal_care"
    SCHOOLWORK = "schoolwork"
    TIDYING = "tidying"
    MEALS = "meals"
    OTHER = "other"


class RedemptionState(str, enum.Enum):
    """State machine for a parent-approved reward redemption.

    Lives in `core.enums` with the other domain enums. The state machine
    is `pending_approval → approved | denied`. Deduction of points
    happens at request time (insufficient balance is a 4xx); refund
    happens on `denied` via `bonus_points_total += cost`. Approved
    redemptions don't move points (they were already deducted at
    request time).

    See the rewards-feature commits on feat-reward-catalogue.
    """

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DENIED = "denied"
