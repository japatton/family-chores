"""Pydantic v2 schemas for the HTTP API."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from family_chores.db.models import DisplayMode, InstanceState, RecurrenceType

_VALID_ISO_WEEKDAYS = {1, 2, 3, 4, 5, 6, 7}


# ─── shared ───────────────────────────────────────────────────────────────


class APIErrorBody(BaseModel):
    error: str
    detail: str
    request_id: str


# ─── members ──────────────────────────────────────────────────────────────


class MemberStatsRead(BaseModel):
    points_total: int = 0
    points_this_week: int = 0
    week_anchor: date_type | None = None
    streak: int = 0
    last_all_done_date: date_type | None = None


class MemberRead(BaseModel):
    id: int
    name: str
    slug: str
    avatar: str | None
    color: str
    display_mode: DisplayMode
    requires_approval: bool
    ha_todo_entity_id: str | None
    stats: MemberStatsRead

    model_config = ConfigDict(from_attributes=True)


class MemberCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    avatar: str | None = Field(None, max_length=256)
    color: str = Field("#4f46e5", max_length=16)
    display_mode: DisplayMode = DisplayMode.KID_STANDARD
    requires_approval: bool = False
    ha_todo_entity_id: str | None = Field(None, max_length=128, pattern=r"^todo\.[a-z0-9_]+$")


class MemberUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    avatar: str | None = Field(None, max_length=256)
    color: str | None = Field(None, max_length=16)
    display_mode: DisplayMode | None = None
    requires_approval: bool | None = None
    ha_todo_entity_id: str | None = Field(None, max_length=128, pattern=r"^todo\.[a-z0-9_]+$")


# ─── chores ───────────────────────────────────────────────────────────────


def validate_recurrence_config(rt: RecurrenceType, cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate a recurrence config for a given type, returning the cleaned dict.

    Raises ValueError with a plain-English message on failure.
    """
    cfg = dict(cfg or {})
    if rt in (RecurrenceType.DAILY, RecurrenceType.WEEKDAYS, RecurrenceType.WEEKENDS):
        return {}
    if rt is RecurrenceType.SPECIFIC_DAYS:
        days = cfg.get("days")
        if not isinstance(days, list) or not days:
            raise ValueError("specific_days requires a non-empty 'days' list")
        try:
            day_ints = [int(d) for d in days]
        except (TypeError, ValueError) as exc:
            raise ValueError("specific_days 'days' must be ints") from exc
        if not all(d in _VALID_ISO_WEEKDAYS for d in day_ints):
            raise ValueError("specific_days 'days' must use ISO weekdays 1-7")
        return {"days": sorted(set(day_ints))}
    if rt is RecurrenceType.EVERY_N_DAYS:
        try:
            n = int(cfg.get("n"))
        except (TypeError, ValueError) as exc:
            raise ValueError("every_n_days 'n' must be an integer") from exc
        if n < 1:
            raise ValueError("every_n_days 'n' must be >= 1")
        anchor = cfg.get("anchor")
        if not isinstance(anchor, str):
            raise ValueError("every_n_days 'anchor' must be an ISO date string")
        try:
            date_type.fromisoformat(anchor)
        except ValueError as exc:
            raise ValueError("every_n_days 'anchor' must be a valid ISO date") from exc
        return {"n": n, "anchor": anchor}
    if rt is RecurrenceType.MONTHLY_ON_DATE:
        try:
            day = int(cfg.get("day"))
        except (TypeError, ValueError) as exc:
            raise ValueError("monthly_on_date 'day' must be an integer") from exc
        if not 1 <= day <= 31:
            raise ValueError("monthly_on_date 'day' must be between 1 and 31")
        return {"day": day}
    if rt is RecurrenceType.ONCE:
        when = cfg.get("date")
        if not isinstance(when, str):
            raise ValueError("once 'date' must be an ISO date string")
        try:
            date_type.fromisoformat(when)
        except ValueError as exc:
            raise ValueError("once 'date' must be a valid ISO date") from exc
        return {"date": when}
    raise ValueError(f"unknown recurrence_type {rt}")


class ChoreRead(BaseModel):
    id: int
    name: str
    icon: str | None
    points: int
    description: str | None
    image: str | None
    active: bool
    recurrence_type: RecurrenceType
    recurrence_config: dict[str, Any]
    time_window_start: time_type | None
    time_window_end: time_type | None
    assigned_member_ids: list[int]

    model_config = ConfigDict(from_attributes=True)


class ChoreCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    icon: str | None = Field(None, max_length=64)
    points: int = Field(0, ge=0)
    description: str | None = None
    image: str | None = Field(None, max_length=256)
    active: bool = True
    recurrence_type: RecurrenceType
    recurrence_config: dict[str, Any] = Field(default_factory=dict)
    time_window_start: time_type | None = None
    time_window_end: time_type | None = None
    assigned_member_ids: list[int] = Field(default_factory=list)

    @field_validator("recurrence_config")
    @classmethod
    def _check_cfg(cls, v: dict[str, Any], info) -> dict[str, Any]:
        rt = info.data.get("recurrence_type")
        if rt is None:
            return v
        return validate_recurrence_config(rt, v)


class ChoreUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    icon: str | None = Field(None, max_length=64)
    points: int | None = Field(None, ge=0)
    description: str | None = None
    image: str | None = Field(None, max_length=256)
    active: bool | None = None
    recurrence_type: RecurrenceType | None = None
    recurrence_config: dict[str, Any] | None = None
    time_window_start: time_type | None = None
    time_window_end: time_type | None = None
    assigned_member_ids: list[int] | None = None


# ─── instances ────────────────────────────────────────────────────────────


class InstanceRead(BaseModel):
    id: int
    chore_id: int
    member_id: int
    date: date_type
    state: InstanceState
    completed_at: datetime | None
    approved_at: datetime | None
    approved_by: str | None
    points_awarded: int
    ha_todo_uid: str | None

    model_config = ConfigDict(from_attributes=True)


class RejectRequest(BaseModel):
    reason: str | None = Field(None, max_length=256)


class AdjustPointsRequest(BaseModel):
    delta: int
    reason: str | None = Field(None, max_length=256)


# ─── today view ───────────────────────────────────────────────────────────


class TodayInstance(BaseModel):
    id: int
    chore_id: int
    chore_name: str
    chore_icon: str | None
    points: int
    state: InstanceState
    time_window_start: time_type | None
    time_window_end: time_type | None


class TodayMember(BaseModel):
    id: int
    slug: str
    name: str
    color: str
    avatar: str | None
    display_mode: DisplayMode
    requires_approval: bool
    stats: MemberStatsRead
    today_progress_pct: int
    instances: list[TodayInstance]


class TodayView(BaseModel):
    date: date_type
    members: list[TodayMember]


# ─── auth ─────────────────────────────────────────────────────────────────


class WhoAmI(BaseModel):
    user: str
    parent_pin_set: bool
    parent_mode_active: bool


class SetPinRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")
    current_pin: str | None = Field(None, min_length=4, max_length=8, pattern=r"^\d+$")


class VerifyPinRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


class ClearPinRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


class TokenResponse(BaseModel):
    token: str
    expires_at: int  # unix seconds


# ─── activity log ─────────────────────────────────────────────────────────


class ActivityLogEntry(BaseModel):
    id: int
    ts: datetime
    actor: str
    action: str
    payload: dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class ActivityLogPage(BaseModel):
    entries: list[ActivityLogEntry]
    total: int
    limit: int
    offset: int
