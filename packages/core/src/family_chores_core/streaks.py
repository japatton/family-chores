"""Streak computation + milestone detection.

Streak rules (per prompt §3):
- A day is "all done" iff every one of that member's instances for that date
  ended in state `DONE` (approved). `done_unapproved`, `skipped`, `missed`
  all fail.
- A day with zero instances for this member neither extends nor breaks the
  streak — we skip past it silently.
- The streak is the count of consecutive "all done" days working backwards
  from `as_of`, stopping at the first day with instances that weren't all
  done.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from family_chores_core.enums import InstanceState

STREAK_MILESTONES: tuple[int, ...] = (3, 7, 14, 30, 100)

# Cap the backwards walk. A family-scale app will never hit this, but it
# prevents a buggy data state from producing an infinite-loop symptom.
_MAX_LOOKBACK_DAYS = 365


def is_all_done(states: Iterable[InstanceState]) -> bool:
    states_list = list(states)
    return bool(states_list) and all(s is InstanceState.DONE for s in states_list)


def compute_streak(
    states_by_date: dict[date, list[InstanceState]],
    as_of: date,
    *,
    max_lookback_days: int = _MAX_LOOKBACK_DAYS,
) -> int:
    """Count consecutive all-done days ending at or before `as_of`."""
    streak = 0
    d = as_of
    for _ in range(max_lookback_days):
        states = states_by_date.get(d, [])
        if states:
            if all(s is InstanceState.DONE for s in states):
                streak += 1
            else:
                return streak
        d -= timedelta(days=1)
    return streak


def crossed_milestone(prev_streak: int, new_streak: int) -> int | None:
    """If `new_streak` crossed a milestone since `prev_streak`, return it.

    Only reports the *first* milestone crossed — in the unlikely case that a
    single rollover jumps past two (e.g. a manual stats rebuild after a long
    gap), the larger milestones are silent.
    """
    if new_streak <= prev_streak:
        return None
    for m in STREAK_MILESTONES:
        if prev_streak < m <= new_streak:
            return m
    return None
