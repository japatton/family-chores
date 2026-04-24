"""Week-anchor math for the `points_this_week` reset.

A "week anchor" is the first date of the week that contains some date `d`,
relative to the configured start-of-week (Monday or Sunday). Weekly points
are reset whenever the stored anchor on `member_stats` differs from the
anchor computed for today — that makes the reset idempotent: running
rollover twice on the same day is a no-op the second time.
"""

from __future__ import annotations

from datetime import date, timedelta

_WEEKDAY_BY_NAME = {"monday": 0, "sunday": 6}


def week_anchor_for(d: date, starts_on: str) -> date:
    target = _WEEKDAY_BY_NAME.get(starts_on)
    if target is None:
        raise ValueError(f"invalid week start: {starts_on!r} (expected 'monday' or 'sunday')")
    delta = (d.weekday() - target) % 7
    return d - timedelta(days=delta)


def needs_week_reset(stored_anchor: date | None, today: date, starts_on: str) -> bool:
    return stored_anchor != week_anchor_for(today, starts_on)
