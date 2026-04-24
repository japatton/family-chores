"""Pure recurrence engine.

Each recurrence rule is expressed as a `RecurrenceType` and a small JSON
`config`. `dates_due(rule, config, start, end)` returns every date in
`[start, end]` (inclusive) on which a chore with that rule should have an
instance generated.

No I/O, no DB, no tz math — callers pass date objects already computed in
the user's timezone and this module just iterates.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any

from family_chores_core.enums import RecurrenceType

_VALID_ISO_WEEKDAYS = frozenset({1, 2, 3, 4, 5, 6, 7})


def _daterange(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _parse_iso_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _clamped_monthly_day(year: int, month: int, day: int) -> date:
    """Return the target day, clamped to the last day of the month if needed."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def dates_due(
    recurrence_type: RecurrenceType,
    config: dict[str, Any] | None,
    start: date,
    end: date,
) -> list[date]:
    """Return all dates in `[start, end]` (inclusive) this rule is due on.

    Unknown/invalid configs return `[]` rather than raising — callers treat a
    misconfigured chore as "no instances due" so a data glitch doesn't break
    generation for every other chore.
    """
    if start > end:
        return []
    cfg = config or {}

    if recurrence_type is RecurrenceType.DAILY:
        return list(_daterange(start, end))

    if recurrence_type is RecurrenceType.WEEKDAYS:
        return [d for d in _daterange(start, end) if d.isoweekday() <= 5]

    if recurrence_type is RecurrenceType.WEEKENDS:
        return [d for d in _daterange(start, end) if d.isoweekday() >= 6]

    if recurrence_type is RecurrenceType.SPECIFIC_DAYS:
        raw_days = cfg.get("days", [])
        if not isinstance(raw_days, list) or not raw_days:
            return []
        try:
            days = {int(x) for x in raw_days}
        except (TypeError, ValueError):
            return []
        if not days.issubset(_VALID_ISO_WEEKDAYS):
            return []
        return [d for d in _daterange(start, end) if d.isoweekday() in days]

    if recurrence_type is RecurrenceType.EVERY_N_DAYS:
        try:
            n = int(cfg.get("n", 0))
        except (TypeError, ValueError):
            return []
        if n < 1:
            return []
        anchor = _parse_iso_date(cfg.get("anchor"))
        if anchor is None:
            return []
        return [d for d in _daterange(start, end) if (d - anchor).days % n == 0]

    if recurrence_type is RecurrenceType.MONTHLY_ON_DATE:
        try:
            day = int(cfg.get("day", 0))
        except (TypeError, ValueError):
            return []
        if not 1 <= day <= 31:
            return []
        out: list[date] = []
        y, m = start.year, start.month
        while date(y, m, 1) <= end:
            candidate = _clamped_monthly_day(y, m, day)
            if start <= candidate <= end:
                out.append(candidate)
            m += 1
            if m > 12:
                m = 1
                y += 1
        return out

    if recurrence_type is RecurrenceType.ONCE:
        once = _parse_iso_date(cfg.get("date"))
        if once is None or not (start <= once <= end):
            return []
        return [once]

    return []
