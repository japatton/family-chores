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
from family_chores_core.enums import InstanceState, RecurrenceType

from family_chores_core.time import utcnow
from family_chores.db.base import Base

__all__ = ["InstanceState", "RecurrenceType"]  # explicit re-export

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
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        CheckConstraint("points_total >= 0", name="ck_member_stats_total_nonneg"),
        CheckConstraint("points_this_week >= 0", name="ck_member_stats_week_nonneg"),
        CheckConstraint("streak >= 0", name="ck_member_stats_streak_nonneg"),
    )

    member: Mapped[Member] = relationship(back_populates="stats")


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


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


__all__ = [
    "ActivityLog",
    "AppConfig",
    "Chore",
    "ChoreAssignment",
    "ChoreInstance",
    "DisplayMode",
    "InstanceState",
    "Member",
    "MemberStats",
    "RecurrenceType",
]
