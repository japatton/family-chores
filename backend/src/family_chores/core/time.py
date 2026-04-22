"""Time helpers.

Invariant: every datetime stored in the DB is a **naive UTC** `datetime`.
This module provides the one canonical way to produce those values and the
helpers to convert between UTC and the HA-reported user timezone for
"today"-style calculations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as date_type
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Return the current UTC time as a naive `datetime`.

    Naive (no tzinfo) is the DB storage convention — see module docstring.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def as_utc(dt: datetime) -> datetime:
    """Return `dt` as a naive UTC `datetime` regardless of input tz-awareness."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


def to_local(dt: datetime, tz: str) -> datetime:
    """Convert a naive-UTC `dt` into a tz-aware local `datetime` in `tz`."""
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    return aware.astimezone(ZoneInfo(tz))


def local_today(tz: str, now: datetime | None = None) -> date_type:
    """Return today's date in the given IANA timezone.

    `now` is injected for testability; defaults to `utcnow()`.
    """
    base = now if now is not None else utcnow()
    return to_local(base, tz).date()
