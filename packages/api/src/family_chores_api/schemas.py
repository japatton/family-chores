"""Pydantic v2 schemas for the HTTP API."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from family_chores_db.models import (
    DisplayMode,
    InstanceState,
    RecurrenceType,
    RedemptionState,
)

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
    # Calendar entity ids for this member (DECISIONS §14). Each is a
    # `calendar.*` entity in HA; the kid view shows events from these
    # plus any from `household_settings.shared_calendar_entity_ids`.
    # Empty list = no per-member calendar (still gets shared events).
    calendar_entity_ids: list[str] = Field(default_factory=list)
    stats: MemberStatsRead
    # Per-kid PIN (DECISIONS §17). Boolean only — the hash itself is
    # never exposed via the API. `false` = no PIN set; `true` = the
    # member's view should prompt for a PIN before showing chores.
    pin_set: bool = False

    model_config = ConfigDict(from_attributes=True)


# Per-kid PIN endpoints (DECISIONS §17). Same shape as the parent-PIN
# request schemas but on a different surface — the parent PIN gates
# admin actions; the kid PIN gates a specific member's view. Both are
# soft locks per the threat model.


class MemberPinSetRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


class MemberPinVerifyRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


class MemberPinVerifyResponse(BaseModel):
    """Returned on successful kid-PIN verification.

    The kid PIN doesn't mint a JWT (unlike the parent PIN) — verification
    is per-request and the frontend tracks which member's view has been
    "unlocked" in client-side state. The verified-until timestamp lets
    the SPA compute when to require re-verification (default 1 hour;
    short enough that a kid leaving the tablet logged in doesn't expose
    the panel to a sibling for the rest of the day).
    """

    member_id: int
    verified_until: int  # unix seconds


class MemberPinStatus(BaseModel):
    """Response shape for `/api/members/{slug}/pin` (GET) — discoverability
    helper so the SPA can avoid POSTing `verify` against members with no
    PIN set."""

    member_id: int
    slug: str
    pin_set: bool


def _validate_calendar_entity_ids(v: list[str] | None) -> list[str] | None:
    """Shared validator used by `MemberCreate` and `MemberUpdate` for
    `calendar_entity_ids`. Mirrors the household-settings validator:
    must start with `calendar.`, dedupe, preserve order."""
    if v is None:
        return v
    seen: set[str] = set()
    out: list[str] = []
    for entity_id in v:
        if not isinstance(entity_id, str):
            raise ValueError("entity ids must be strings")
        stripped = entity_id.strip()
        if not stripped:
            continue
        if not stripped.startswith("calendar."):
            raise ValueError(
                f"entity id {stripped!r} must start with 'calendar.'"
            )
        if stripped in seen:
            continue
        seen.add(stripped)
        out.append(stripped)
    return out


class MemberCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    slug: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    avatar: str | None = Field(None, max_length=256)
    color: str = Field("#4f46e5", max_length=16)
    display_mode: DisplayMode = DisplayMode.KID_STANDARD
    requires_approval: bool = False
    ha_todo_entity_id: str | None = Field(None, max_length=128, pattern=r"^todo\.[a-z0-9_]+$")
    calendar_entity_ids: list[str] = Field(default_factory=list)

    @field_validator("calendar_entity_ids")
    @classmethod
    def _validate_calendar_ids(cls, v: list[str]) -> list[str]:
        # `_validate_calendar_entity_ids` returns `None` only for `None`
        # input — Create always supplies a list (default empty), so the
        # `or []` here is just to satisfy mypy's narrower return type.
        return _validate_calendar_entity_ids(v) or []


class MemberUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    avatar: str | None = Field(None, max_length=256)
    color: str | None = Field(None, max_length=16)
    display_mode: DisplayMode | None = None
    requires_approval: bool | None = None
    ha_todo_entity_id: str | None = Field(None, max_length=128, pattern=r"^todo\.[a-z0-9_]+$")
    calendar_entity_ids: list[str] | None = None

    @field_validator("calendar_entity_ids")
    @classmethod
    def _validate_calendar_ids(cls, v: list[str] | None) -> list[str] | None:
        return _validate_calendar_entity_ids(v)


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
        n_raw = cfg.get("n")
        if n_raw is None:
            raise ValueError("every_n_days 'n' is required")
        try:
            n = int(n_raw)
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
        day_raw = cfg.get("day")
        if day_raw is None:
            raise ValueError("monthly_on_date 'day' is required")
        try:
            day = int(day_raw)
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
    # Chore-templates feature (DECISIONS §13). Records which template this
    # chore was spawned from, if any. Informational only — nothing in the
    # service layer branches on it.
    template_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ChoreCreateResult(ChoreRead):
    """ChoreRead + a one-shot signal indicating whether a brand-new
    suggestion was created alongside this chore.

    Used only as the POST /api/chores response body; PATCH and GET keep
    returning ChoreRead. The frontend reads `template_created` to flash
    a subtle "saved as a suggestion for next time" toast.
    """

    template_created: bool = False


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
    # Chore-templates feature (DECISIONS §13). `template_id` is the
    # source-template hint; if set, the router validates it exists in
    # this household and records it on the new chore. `save_as_suggestion`
    # defaults to True per §6.1 (the dialog checkbox is pre-checked).
    template_id: str | None = Field(None, max_length=36)
    save_as_suggestion: bool = True

    @field_validator("recurrence_config")
    @classmethod
    def _check_cfg(
        cls, v: dict[str, Any], info: Any
    ) -> dict[str, Any]:
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
    reason: Annotated[str | None, Field(max_length=256)] = None


class AdjustPointsRequest(BaseModel):
    delta: int
    reason: Annotated[str | None, Field(max_length=256)] = None


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


# ─── suggestions (chore templates) ────────────────────────────────────────


class SuggestionRead(BaseModel):
    """Outward shape of a chore_template row.

    `name_normalized` is internal — populated by the service layer from
    `normalize_chore_name(name)` and used for dedup. Not exposed.
    `household_id` is also intentionally not exposed; the API is already
    scoped to the caller's household and surfacing it would just confuse
    the UI.
    """

    id: str
    name: str
    icon: str | None
    category: str | None
    age_min: int | None
    age_max: int | None
    points_suggested: int
    default_recurrence_type: RecurrenceType
    default_recurrence_config: dict[str, Any]
    description: str | None
    source: str  # 'starter' | 'custom'
    starter_key: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SuggestionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    icon: str | None = Field(None, max_length=64)
    category: str | None = Field(None, max_length=32)
    age_min: int | None = Field(None, ge=0, le=120)
    age_max: int | None = Field(None, ge=0, le=120)
    points_suggested: int = Field(1, ge=0)
    default_recurrence_type: RecurrenceType
    default_recurrence_config: dict[str, Any] = Field(default_factory=dict)
    description: str | None = Field(None, max_length=2048)

    @field_validator("default_recurrence_config")
    @classmethod
    def _check_cfg(
        cls, v: dict[str, Any], info: Any
    ) -> dict[str, Any]:
        rt = info.data.get("default_recurrence_type")
        if rt is None:
            return v
        return validate_recurrence_config(rt, v)

    @field_validator("age_max")
    @classmethod
    def _check_ages(cls, v: int | None, info: Any) -> int | None:
        a_min = info.data.get("age_min")
        if v is not None and a_min is not None and v < a_min:
            raise ValueError("age_max must be >= age_min")
        return v


class SuggestionUpdate(BaseModel):
    """All fields optional. The service layer rejects edits to
    starter-template names (starter `name` is immutable; other fields
    are editable per DECISIONS §13 §1.2)."""

    name: str | None = Field(None, min_length=1, max_length=120)
    icon: str | None = Field(None, max_length=64)
    category: str | None = Field(None, max_length=32)
    age_min: int | None = Field(None, ge=0, le=120)
    age_max: int | None = Field(None, ge=0, le=120)
    points_suggested: int | None = Field(None, ge=0)
    default_recurrence_type: RecurrenceType | None = None
    default_recurrence_config: dict[str, Any] | None = None
    description: str | None = Field(None, max_length=2048)


class SuggestionResetResult(BaseModel):
    """Returned from POST /api/suggestions/reset."""

    suppressions_cleared: int
    seeded: int
    library_version: int


# ─── rewards + redemptions ────────────────────────────────────────────────


class RewardRead(BaseModel):
    id: str
    name: str
    description: str | None
    cost_points: int
    icon: str | None
    active: bool
    max_per_week: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RewardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2048)
    cost_points: int = Field(..., gt=0, le=1_000_000)
    icon: str | None = Field(None, max_length=64)
    active: bool = True
    max_per_week: int | None = Field(None, gt=0, le=100)


class RewardUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, max_length=2048)
    cost_points: int | None = Field(None, gt=0, le=1_000_000)
    icon: str | None = Field(None, max_length=64)
    active: bool | None = None
    max_per_week: int | None = Field(None, gt=0, le=100)


class RedemptionRead(BaseModel):
    id: str
    reward_id: str
    member_id: int
    state: RedemptionState
    cost_points_at_redeem: int
    reward_name_at_redeem: str
    requested_at: datetime
    actor_requested: str | None
    approved_at: datetime | None
    approved_by: str | None
    denied_at: datetime | None
    denied_by: str | None
    denied_reason: str | None

    model_config = ConfigDict(from_attributes=True)


class RedemptionCreate(BaseModel):
    """Body for `POST /api/members/{slug}/redemptions` (kid-facing).

    The reward_id selects which reward; the member is resolved from
    the URL path.
    """

    reward_id: str = Field(..., min_length=1, max_length=36)


class RedemptionDenyRequest(BaseModel):
    reason: str | None = Field(None, max_length=256)


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


# ─── calendar (DECISIONS §14) ─────────────────────────────────────────────
#
# `CalendarEventRead` mirrors `services.calendar.CalendarEvent` —
# `RawEvent` plus parsed prep items. The router serialises the
# service-layer dataclass directly through this schema (Pydantic
# accepts the dataclass via `from_attributes=True`).


class CalendarPrepItemRead(BaseModel):
    label: str
    icon: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CalendarEventRead(BaseModel):
    entity_id: str
    summary: str
    description: str | None
    start: datetime
    end: datetime
    all_day: bool
    location: str | None
    prep_items: list[CalendarPrepItemRead]

    model_config = ConfigDict(from_attributes=True)


class CalendarWindowRead(BaseModel):
    """Response shape for `/api/calendar/events`. `unreachable` lets the
    UI render a per-tile error state for any calendar entity that
    couldn't be reached this fetch (DECISIONS §14 Q11)."""

    events: list[CalendarEventRead]
    unreachable: list[str]


class CalendarRefreshResponse(BaseModel):
    """Response from `POST /api/calendar/refresh` — how many cache
    entries were dropped (mostly informational; the SPA just needs
    to know the call succeeded)."""

    invalidated: int


# ─── household settings (DECISIONS §14) ──────────────────────────────────
#
# Single-row-per-household configuration. First column is the family-
# shared calendar entity list; future settings (default member display
# mode, week-start-day, etc.) land here too.


class HouseholdSettingsRead(BaseModel):
    shared_calendar_entity_ids: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class HouseholdSettingsUpdate(BaseModel):
    """PUT body — `None` means "leave unchanged" so the SPA can patch
    one field at a time without sending the whole row."""

    shared_calendar_entity_ids: list[str] | None = Field(
        None,
        description=(
            "List of HA `calendar.*` entity ids that show up on every "
            "member's view (the family-shared layer)."
        ),
    )

    @field_validator("shared_calendar_entity_ids")
    @classmethod
    def _validate_entity_ids(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        # De-dupe while preserving order so the parent's intended
        # display sequence sticks.
        seen: set[str] = set()
        out: list[str] = []
        for entity_id in v:
            if not isinstance(entity_id, str):
                raise ValueError("entity ids must be strings")
            stripped = entity_id.strip()
            if not stripped:
                continue
            if not stripped.startswith("calendar."):
                raise ValueError(
                    f"entity id {stripped!r} must start with 'calendar.'"
                )
            if stripped in seen:
                continue
            seen.add(stripped)
            out.append(stripped)
        return out
