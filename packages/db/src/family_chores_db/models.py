"""ORM models.

Conventions:
- Table names are plural snake_case.
- All timestamps are naive UTC datetimes. Python-side defaults (`utcnow`) are
  used rather than `server_default`/SQL defaults so the convention stays
  identical across SQLAlchemy dialects and is unambiguous for tests.
- Enums are stored as strings (`native_enum=False`) so adding a new enum
  value is a pure code change with no schema migration needed.
"""

from __future__ import annotations

import enum
from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# `RecurrenceType` and `InstanceState` are *domain* enums — used by both the
# DB layer (here, to type columns) and `family_chores_core` (to reason about
# recurrence + streaks). They live in `family_chores_core.enums` so the
# core ↔ db arrow stays one-way (see DECISIONS §11 step 2). Re-exported here
# so existing `from family_chores.db.models import RecurrenceType` callsites
# keep working without a sweep.
from family_chores_core.enums import InstanceState, RecurrenceType, RedemptionState

from family_chores_core.time import utcnow
from family_chores_db.base import Base

__all__ = ["InstanceState", "RecurrenceType", "RedemptionState"]  # explicit re-export

# ─── enums ───────────────────────────────────────────────────────────────


class DisplayMode(str, enum.Enum):
    """Member-presentation preference. Stays in db.models — not domain logic."""

    KID_LARGE = "kid_large"
    KID_STANDARD = "kid_standard"
    TEEN = "teen"


def _display_mode_col() -> SQLEnum:
    return SQLEnum(DisplayMode, name="display_mode", native_enum=False, length=16)


def _recurrence_type_col() -> SQLEnum:
    return SQLEnum(RecurrenceType, name="recurrence_type", native_enum=False, length=32)


def _instance_state_col() -> SQLEnum:
    return SQLEnum(InstanceState, name="instance_state", native_enum=False, length=32)


# ─── tables ──────────────────────────────────────────────────────────────


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(256))
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#4f46e5")
    display_mode: Mapped[DisplayMode] = mapped_column(
        _display_mode_col(), nullable=False, default=DisplayMode.KID_STANDARD
    )
    requires_approval: Mapped[bool] = mapped_column(nullable=False, default=False)
    # Entity_id of a Local To-do list in HA, e.g. "todo.alice_chores". If
    # unset the bridge skips todo sync for this member but still publishes
    # sensors and events. See INSTALL.md "HA Todo Setup".
    ha_todo_entity_id: Mapped[str | None] = mapped_column(String(128))
    # Per-member soft-lock PIN hash (DECISIONS §17). Same threat model as
    # the parent PIN — convenience gate, not a security boundary. NULL =
    # no per-member PIN set. Argon2-hashed via the same helpers as the
    # parent PIN.
    pin_hash: Mapped[str | None] = mapped_column(String(256))
    # Per-member calendar mapping (DECISIONS §14). List of HA `calendar.*`
    # entity IDs the parent has assigned to this member. Empty list = no
    # calendars mapped. Per-member privacy lives here — events on a
    # parent's work calendar aren't mapped to any kid.
    #
    # `server_default` matters for the test_startup_recovery path which
    # creates tables via `Base.metadata.create_all` (not via Alembic).
    # The Python-side `default=list` only fires on ORM inserts; the
    # server-side default catches raw SQL inserts that omit the column.
    calendar_entity_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    # Tenant scope (step 8). NULL in single-tenant add-on mode — the
    # service-layer `scoped()` helper (step 9) treats NULL as "no filter".
    household_id: Mapped[str | None] = mapped_column(String(36))

    assigned_chores: Mapped[list[Chore]] = relationship(
        secondary="chore_assignments", back_populates="assigned_members"
    )
    instances: Mapped[list[ChoreInstance]] = relationship(
        back_populates="member", cascade="all, delete-orphan", passive_deletes=True
    )
    stats: Mapped[MemberStats | None] = relationship(
        back_populates="member",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Chore(Base):
    __tablename__ = "chores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(64))
    points: Mapped[int] = mapped_column(nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(nullable=False, default=True, index=True)
    recurrence_type: Mapped[RecurrenceType] = mapped_column(_recurrence_type_col(), nullable=False)
    recurrence_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    time_window_start: Mapped[time_type | None] = mapped_column(Time)
    time_window_end: Mapped[time_type | None] = mapped_column(Time)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    # Tenant scope (step 8). See `Member.household_id`.
    household_id: Mapped[str | None] = mapped_column(String(36))
    # Chore-templates feature (DECISIONS §13). `template_id` records the
    # template the chore was spawned from, if any — informational only.
    # `ON DELETE SET NULL` so deleting a template doesn't cascade to its
    # spawned chores. `ephemeral=True` means "this chore did NOT save
    # itself as a suggestion" — currently informational, retained for a
    # future "save this chore as a suggestion" retrofit action.
    template_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("chore_template.id", ondelete="SET NULL"),
        index=True,
    )
    ephemeral: Mapped[bool] = mapped_column(nullable=False, default=False)

    __table_args__ = (CheckConstraint("points >= 0", name="ck_chores_points_nonneg"),)

    assigned_members: Mapped[list[Member]] = relationship(
        secondary="chore_assignments", back_populates="assigned_chores"
    )
    instances: Mapped[list[ChoreInstance]] = relationship(
        back_populates="chore", cascade="all, delete-orphan", passive_deletes=True
    )


class ChoreAssignment(Base):
    __tablename__ = "chore_assignments"

    chore_id: Mapped[int] = mapped_column(
        ForeignKey("chores.id", ondelete="CASCADE"), primary_key=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    # Tenant scope (step 8). Stored on the join row directly so scoped
    # queries don't need a join through chore or member.
    household_id: Mapped[str | None] = mapped_column(String(36))


class ChoreInstance(Base):
    __tablename__ = "chore_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    chore_id: Mapped[int] = mapped_column(
        ForeignKey("chores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False, index=True)
    state: Mapped[InstanceState] = mapped_column(
        _instance_state_col(), nullable=False, default=InstanceState.PENDING, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    points_awarded: Mapped[int] = mapped_column(nullable=False, default=0)
    ha_todo_uid: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    # Tenant scope (step 8). See `Member.household_id`.
    household_id: Mapped[str | None] = mapped_column(String(36))

    __table_args__ = (
        UniqueConstraint("chore_id", "member_id", "date", name="uq_chore_instances_cmd"),
        CheckConstraint("points_awarded >= 0", name="ck_chore_instances_points_nonneg"),
        Index("ix_chore_instances_member_date", "member_id", "date"),
    )

    chore: Mapped[Chore] = relationship(back_populates="instances")
    member: Mapped[Member] = relationship(back_populates="instances")


class MemberStats(Base):
    __tablename__ = "member_stats"

    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), primary_key=True
    )
    points_total: Mapped[int] = mapped_column(nullable=False, default=0)
    points_this_week: Mapped[int] = mapped_column(nullable=False, default=0)
    week_anchor: Mapped[date_type | None] = mapped_column(Date)
    streak: Mapped[int] = mapped_column(nullable=False, default=0)
    last_all_done_date: Mapped[date_type | None] = mapped_column(Date)
    # Cumulative parent-applied adjustments via /api/members/{id}/points/adjust.
    # Recompute folds this into `points_total` so adjustments survive the
    # midnight rollover (DECISIONS §16, F-S001 fix). Signed — a negative
    # cumulative bonus represents a net penalty that the member earns back
    # through chore completions before their displayed `points_total` rises.
    bonus_points_total: Mapped[int] = mapped_column(nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    # Tenant scope (step 8). See `Member.household_id`.
    household_id: Mapped[str | None] = mapped_column(String(36))

    __table_args__ = (
        CheckConstraint("points_total >= 0", name="ck_member_stats_total_nonneg"),
        CheckConstraint("points_this_week >= 0", name="ck_member_stats_week_nonneg"),
        CheckConstraint("streak >= 0", name="ck_member_stats_streak_nonneg"),
        # Deliberately no `bonus_points_total >= 0` — see DECISIONS §16.
    )

    member: Mapped[Member] = relationship(back_populates="stats")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    # Tenant scope (step 8). See `Member.household_id`.
    household_id: Mapped[str | None] = mapped_column(String(36))


class AppConfig(Base):
    """Simple key-value store for runtime secrets and cached HA state.

    Known keys:
      - `parent_pin_hash` — argon2 hash (str)
      - `jwt_secret` — base64-encoded random bytes (str)
      - `timezone_override` — IANA tz name (str) or absent
      - `bootstrap_banner` — `{"message": str, "ts": iso8601}` or absent
      - `ha_tz_cached` — `{"tz": str, "fetched_at": iso8601}` or absent
    """

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    # Tenant scope (step 8). See `Member.household_id`. Each household has
    # its own jwt_secret / parent_pin_hash / etc. once multi-tenant lands.
    household_id: Mapped[str | None] = mapped_column(String(36))


class ChoreTemplate(Base):
    """Reusable blueprint for creating chores. See DECISIONS §13.

    Templates and chores are independent — editing a template does NOT
    modify any chore that was spawned from it, and editing a chore does
    NOT modify its source template. The chore↔template split is invisible
    to the parent UI (which talks about "suggestions"); this class is
    only ever named `chore_template` in code.

    `source='starter'` rows come from the bundled library at
    `packages/core/.../data/starter_library.json`. `source='custom'` rows
    are parent-created via the API. Starter rows can be soft-deleted
    via `household_starter_suppression`; custom rows are hard-deleted.

    SQLite-specific dedup gotcha: the `(household_id, name_normalized)`
    and `(household_id, starter_key)` unique constraints DO NOT fire
    when `household_id IS NULL` (SQLite treats NULL as distinct in
    UNIQUE per the SQL standard). In single-tenant addon mode every
    row has `household_id=NULL`, so dedup is enforced at the
    application layer (seeder SELECTs first; API router returns 409
    on conflict) rather than by the constraint. The constraint
    becomes load-bearing in multi-tenant SaaS where `household_id` is
    non-null.
    """

    __tablename__ = "chore_template"

    # UUID-style string PK (vs the integer PKs elsewhere in this file)
    # so the seeder can assign deterministic IDs and so future SaaS
    # cross-system references aren't tied to a per-DB autoincrement.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Tenant scope. NULL in single-tenant addon mode (matches the rest of
    # the schema; see Member.household_id and DECISIONS §11 step 8).
    household_id: Mapped[str | None] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Populated by the service layer from `normalize_chore_name(name)`
    # (packages/core/.../naming.py). Never editable directly via API —
    # recomputed on every name update.
    name_normalized: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    icon: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(32), index=True)
    age_min: Mapped[int | None] = mapped_column()
    age_max: Mapped[int | None] = mapped_column()
    points_suggested: Mapped[int] = mapped_column(nullable=False, default=1)
    default_recurrence_type: Mapped[RecurrenceType] = mapped_column(
        _recurrence_type_col(), nullable=False
    )
    default_recurrence_config: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    description: Mapped[str | None] = mapped_column(Text)
    # 'starter' or 'custom'. Plain string column with a CHECK constraint
    # rather than SQLEnum — keeps adding values a pure code change with
    # no migration (same rationale as RecurrenceType, see file header).
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="custom")
    # Set only for source='starter' rows. Combined with `household_id` in
    # the (household_id, starter_key) unique constraint so the seeder can
    # detect "already seeded" via SELECT and the suppression table can
    # remember "deliberately deleted" across upgrade runs.
    starter_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "household_id", "name_normalized", name="uq_template_household_name"
        ),
        UniqueConstraint(
            "household_id", "starter_key", name="uq_template_household_starter_key"
        ),
        Index("ix_template_household_category", "household_id", "category"),
        CheckConstraint("points_suggested >= 0", name="ck_template_points_nonneg"),
        CheckConstraint("source IN ('starter', 'custom')", name="ck_template_source_enum"),
    )


class HouseholdStarterSuppression(Base):
    """Records starter templates a parent has deleted.

    Without this, the seeder would re-create deleted starter templates
    on every addon startup (since seeding runs unconditionally — see
    DECISIONS §13 §4.2). When a parent deletes a starter template, the
    starter row is hard-deleted from `chore_template` and an entry is
    inserted here so the next seeding pass skips that key.

    The "Reset starter suggestions" API endpoint clears these rows for a
    household and re-runs the seeder, restoring everything the parent
    had deleted. Documented in DOCS.md as an escape hatch.

    Composite PK on (household_id, starter_key). SQLite allows NULL in
    composite PK columns and treats NULLs as distinct, so single-tenant
    mode (all rows have `household_id=NULL`) cannot rely on the PK to
    prevent double-suppression — the seeder/API does an existence check
    before inserting. The composite PK is still the right shape for
    multi-tenant SaaS where `household_id` is non-null.
    """

    __tablename__ = "household_starter_suppression"

    household_id: Mapped[str | None] = mapped_column(String(36), primary_key=True)
    starter_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    suppressed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )


class Reward(Base):
    """Parent-defined catalogue row.

    Soft-deleted via `active=False` rather than hard-deleted — historical
    redemption rows hold a `RESTRICT` foreign key to `reward.id`, so a
    hard delete with active redemptions would fail at the DB level. The
    soft path lets the parent retire a reward without losing the
    audit history of who redeemed it for what cost when.
    """

    __tablename__ = "reward"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cost_points: Mapped[int] = mapped_column(nullable=False)
    icon: Mapped[str | None] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    # Optional weekly cap on per-member redemptions of this reward. NULL =
    # no cap. Enforced at request time by the service layer (counts the
    # member's redemptions of this reward in the current week_anchor
    # window, including denied ones).
    max_per_week: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("cost_points > 0", name="ck_reward_cost_positive"),
        CheckConstraint(
            "max_per_week IS NULL OR max_per_week > 0",
            name="ck_reward_max_per_week_positive",
        ),
        Index("ix_reward_household_active", "household_id", "active"),
    )


class Redemption(Base):
    """A kid-initiated request to redeem a reward.

    State machine: `pending_approval → approved | denied`. Points are
    deducted at request time (insufficient balance is a 4xx, points
    don't move). Approved = no points change; denied = refund via
    `MemberStats.bonus_points_total += cost`.

    The `*_at_redeem` snapshot fields capture what the reward looked
    like at request time so a parent renaming/repricing the reward
    later doesn't change historical records.
    """

    __tablename__ = "redemption"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[str | None] = mapped_column(String(36))
    reward_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reward.id", ondelete="RESTRICT"),
        nullable=False,
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[RedemptionState] = mapped_column(
        SQLEnum(
            RedemptionState,
            name="redemption_state",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    cost_points_at_redeem: Mapped[int] = mapped_column(nullable=False)
    reward_name_at_redeem: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    actor_requested: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    denied_at: Mapped[datetime | None] = mapped_column(DateTime)
    denied_by: Mapped[str | None] = mapped_column(String(128))
    denied_reason: Mapped[str | None] = mapped_column(String(256))

    __table_args__ = (
        CheckConstraint(
            "cost_points_at_redeem > 0", name="ck_redemption_cost_positive"
        ),
        Index("ix_redemption_household_state", "household_id", "state"),
        Index("ix_redemption_member", "member_id", "requested_at"),
    )


class HouseholdSettings(Base):
    """Single-row-per-household configuration table (DECISIONS §14).

    The existing `app_config` bag is key/value and used for runtime-
    minted things (JWT secret, parent PIN hash). `household_settings`
    is for parent-curated, structured household-level config that's
    cleaner as named columns than as opaque JSON values in app_config.

    First column: `shared_calendar_entity_ids` for the calendar
    integration's family-shared mapping. Future additions land here
    too (week-start-day moved here later, default member display
    mode, etc.).

    Single-tenant addon mode keeps `household_id = NULL`; the PK is
    just that one column.
    """

    __tablename__ = "household_settings"

    household_id: Mapped[str | None] = mapped_column(
        String(36), primary_key=True
    )
    shared_calendar_entity_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


__all__ = [
    "ActivityLog",
    "AppConfig",
    "Chore",
    "ChoreAssignment",
    "ChoreInstance",
    "ChoreTemplate",
    "DisplayMode",
    "HouseholdSettings",
    "HouseholdStarterSuppression",
    "InstanceState",
    "Member",
    "MemberStats",
    "RecurrenceType",
    "Redemption",
    "RedemptionState",
    "Reward",
]
