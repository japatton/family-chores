"""Tests for streak computation + milestone detection."""

from __future__ import annotations

from datetime import date, timedelta

from family_chores_core.enums import InstanceState
from family_chores_core.streaks import (
    STREAK_MILESTONES,
    compute_streak,
    crossed_milestone,
    is_all_done,
)


def test_is_all_done_empty_is_false():
    assert is_all_done([]) is False


def test_is_all_done_all_done_is_true():
    assert is_all_done([InstanceState.DONE, InstanceState.DONE]) is True


def test_is_all_done_any_non_done_is_false():
    for s in (
        InstanceState.PENDING,
        InstanceState.MISSED,
        InstanceState.SKIPPED,
        InstanceState.DONE_UNAPPROVED,
    ):
        assert is_all_done([InstanceState.DONE, s]) is False


def test_compute_streak_empty_history():
    assert compute_streak({}, date(2026, 4, 21)) == 0


def test_compute_streak_counts_back_from_as_of():
    history = {
        date(2026, 4, 19): [InstanceState.DONE, InstanceState.DONE],
        date(2026, 4, 20): [InstanceState.DONE],
        date(2026, 4, 21): [InstanceState.DONE, InstanceState.DONE],
    }
    assert compute_streak(history, date(2026, 4, 21)) == 3


def test_compute_streak_zero_instance_day_is_skipped_not_broken():
    history = {
        date(2026, 4, 19): [InstanceState.DONE],
        # 2026-04-20 has no instances — e.g. all chores inactive that day
        date(2026, 4, 21): [InstanceState.DONE],
    }
    assert compute_streak(history, date(2026, 4, 21)) == 2


def test_compute_streak_breaks_on_non_done_day():
    history = {
        date(2026, 4, 18): [InstanceState.DONE],
        date(2026, 4, 19): [InstanceState.MISSED],  # breaks here
        date(2026, 4, 20): [InstanceState.DONE],
        date(2026, 4, 21): [InstanceState.DONE],
    }
    assert compute_streak(history, date(2026, 4, 21)) == 2


def test_compute_streak_breaks_on_partially_done_day():
    history = {
        date(2026, 4, 20): [InstanceState.DONE, InstanceState.MISSED],  # partial
        date(2026, 4, 21): [InstanceState.DONE],
    }
    assert compute_streak(history, date(2026, 4, 21)) == 1


def test_compute_streak_done_unapproved_does_not_count():
    """Per the literal reading of the prompt — `done_unapproved` is not
    `done`, so it ends the streak until approval."""
    history = {
        date(2026, 4, 20): [InstanceState.DONE_UNAPPROVED],
        date(2026, 4, 21): [InstanceState.DONE],
    }
    assert compute_streak(history, date(2026, 4, 21)) == 1


def test_compute_streak_as_of_in_the_middle():
    history = {
        date(2026, 4, 19): [InstanceState.DONE],
        date(2026, 4, 20): [InstanceState.DONE],
        date(2026, 4, 21): [InstanceState.MISSED],
    }
    # Asking for streak as of 2026-04-20 — shouldn't see 2026-04-21's break.
    assert compute_streak(history, date(2026, 4, 20)) == 2


def test_compute_streak_skips_leading_zero_days():
    history = {
        # as_of = 2026-04-21, but we've done nothing that day yet —
        # the walk skips it and evaluates yesterday.
        date(2026, 4, 20): [InstanceState.DONE],
    }
    assert compute_streak(history, date(2026, 4, 21)) == 1


def test_compute_streak_lookback_cap():
    # An unbroken DONE chain back to the dawn of time is capped at the
    # lookback window — prevents runaway loops on bad data.
    end = date(2026, 4, 21)
    history = {end - timedelta(days=i): [InstanceState.DONE] for i in range(40)}
    assert compute_streak(history, end, max_lookback_days=20) == 20


# ─── milestones ───────────────────────────────────────────────────────────


def test_milestones_order_is_ascending_and_unique():
    assert list(STREAK_MILESTONES) == sorted(set(STREAK_MILESTONES))
    assert STREAK_MILESTONES == (3, 7, 14, 30, 100)


def test_crossed_milestone_returns_first_crossed():
    assert crossed_milestone(2, 3) == 3
    assert crossed_milestone(6, 7) == 7
    assert crossed_milestone(0, 3) == 3  # jumped past start
    # Jump past two in a single tick — returns only the first.
    assert crossed_milestone(2, 8) == 3


def test_crossed_milestone_returns_none_when_not_crossed():
    assert crossed_milestone(3, 3) is None
    assert crossed_milestone(7, 8) is None
    assert crossed_milestone(4, 6) is None


def test_crossed_milestone_regression_ignored():
    assert crossed_milestone(10, 5) is None
    assert crossed_milestone(100, 3) is None
