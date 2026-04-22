"""Tests for the recurrence engine."""

from __future__ import annotations

from datetime import date

import pytest

from family_chores.core.recurrence import dates_due
from family_chores.db.models import RecurrenceType


# ─── daily / weekday / weekend ────────────────────────────────────────────


def test_daily_inclusive_range():
    out = dates_due(RecurrenceType.DAILY, None, date(2026, 4, 20), date(2026, 4, 22))
    assert out == [date(2026, 4, 20), date(2026, 4, 21), date(2026, 4, 22)]


def test_daily_single_day():
    out = dates_due(RecurrenceType.DAILY, None, date(2026, 4, 20), date(2026, 4, 20))
    assert out == [date(2026, 4, 20)]


def test_weekdays_filters_saturday_sunday():
    # 2026-04-20 is Monday, 2026-04-26 is Sunday
    out = dates_due(RecurrenceType.WEEKDAYS, None, date(2026, 4, 20), date(2026, 4, 26))
    assert [d.isoweekday() for d in out] == [1, 2, 3, 4, 5]


def test_weekends_includes_saturday_and_sunday_only():
    out = dates_due(RecurrenceType.WEEKENDS, None, date(2026, 4, 20), date(2026, 4, 26))
    assert [d.isoweekday() for d in out] == [6, 7]


# ─── specific_days ────────────────────────────────────────────────────────


def test_specific_days_mwf():
    cfg = {"days": [1, 3, 5]}  # Mon, Wed, Fri
    out = dates_due(RecurrenceType.SPECIFIC_DAYS, cfg, date(2026, 4, 20), date(2026, 4, 26))
    assert [d.isoweekday() for d in out] == [1, 3, 5]


def test_specific_days_empty_list_returns_nothing():
    out = dates_due(RecurrenceType.SPECIFIC_DAYS, {"days": []}, date(2026, 4, 20), date(2026, 4, 26))
    assert out == []


def test_specific_days_invalid_weekday_returns_nothing():
    out = dates_due(
        RecurrenceType.SPECIFIC_DAYS, {"days": [0, 8]}, date(2026, 4, 20), date(2026, 4, 26)
    )
    assert out == []


def test_specific_days_handles_string_ints():
    # JSON from the browser might send strings — we coerce.
    out = dates_due(
        RecurrenceType.SPECIFIC_DAYS,
        {"days": ["1", "5"]},
        date(2026, 4, 20),
        date(2026, 4, 26),
    )
    assert [d.isoweekday() for d in out] == [1, 5]


# ─── every_n_days ─────────────────────────────────────────────────────────


def test_every_n_days_every_third():
    cfg = {"n": 3, "anchor": "2026-01-01"}
    out = dates_due(RecurrenceType.EVERY_N_DAYS, cfg, date(2026, 1, 1), date(2026, 1, 10))
    assert out == [date(2026, 1, 1), date(2026, 1, 4), date(2026, 1, 7), date(2026, 1, 10)]


def test_every_n_days_with_future_anchor():
    # Anchor is in the future — should still produce correct offsets.
    cfg = {"n": 3, "anchor": "2026-04-28"}
    out = dates_due(RecurrenceType.EVERY_N_DAYS, cfg, date(2026, 4, 20), date(2026, 4, 28))
    # (d - anchor).days % 3 == 0 → 2026-04-22 and 2026-04-25 and 2026-04-28
    assert out == [date(2026, 4, 22), date(2026, 4, 25), date(2026, 4, 28)]


def test_every_n_days_invalid_n_returns_nothing():
    for bad in ({"n": 0, "anchor": "2026-01-01"}, {"n": -1, "anchor": "2026-01-01"}, {}):
        assert dates_due(RecurrenceType.EVERY_N_DAYS, bad, date(2026, 1, 1), date(2026, 1, 31)) == []


def test_every_n_days_missing_anchor_returns_nothing():
    assert dates_due(RecurrenceType.EVERY_N_DAYS, {"n": 2}, date(2026, 1, 1), date(2026, 1, 31)) == []


# ─── monthly_on_date ──────────────────────────────────────────────────────


def test_monthly_on_date_basic():
    cfg = {"day": 15}
    out = dates_due(RecurrenceType.MONTHLY_ON_DATE, cfg, date(2026, 1, 1), date(2026, 3, 31))
    assert out == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]


def test_monthly_on_date_31_clamps_to_month_end():
    cfg = {"day": 31}
    out = dates_due(RecurrenceType.MONTHLY_ON_DATE, cfg, date(2026, 1, 1), date(2026, 4, 30))
    # Jan 31, Feb 28 (2026 non-leap), Mar 31, Apr 30
    assert out == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]


def test_monthly_on_date_feb_29_leap_year():
    cfg = {"day": 29}
    out = dates_due(RecurrenceType.MONTHLY_ON_DATE, cfg, date(2024, 2, 1), date(2024, 3, 31))
    # 2024 is a leap year, so Feb 29 exists
    assert out == [date(2024, 2, 29), date(2024, 3, 29)]


def test_monthly_on_date_feb_29_non_leap_clamps_to_28():
    cfg = {"day": 29}
    out = dates_due(RecurrenceType.MONTHLY_ON_DATE, cfg, date(2025, 2, 1), date(2025, 2, 28))
    assert out == [date(2025, 2, 28)]


def test_monthly_on_date_crosses_year_boundary():
    cfg = {"day": 1}
    out = dates_due(RecurrenceType.MONTHLY_ON_DATE, cfg, date(2025, 11, 1), date(2026, 2, 28))
    assert out == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


def test_monthly_on_date_invalid_day():
    for bad in ({"day": 0}, {"day": 32}, {}, {"day": "abc"}):
        assert (
            dates_due(RecurrenceType.MONTHLY_ON_DATE, bad, date(2026, 1, 1), date(2026, 12, 31))
            == []
        )


# ─── once ─────────────────────────────────────────────────────────────────


def test_once_in_range():
    cfg = {"date": "2026-05-01"}
    out = dates_due(RecurrenceType.ONCE, cfg, date(2026, 4, 20), date(2026, 5, 4))
    assert out == [date(2026, 5, 1)]


def test_once_outside_range():
    cfg = {"date": "2027-01-01"}
    out = dates_due(RecurrenceType.ONCE, cfg, date(2026, 4, 20), date(2026, 5, 4))
    assert out == []


def test_once_invalid_date_string():
    cfg = {"date": "nope"}
    assert dates_due(RecurrenceType.ONCE, cfg, date(2026, 4, 20), date(2026, 5, 4)) == []


# ─── boundary conditions ──────────────────────────────────────────────────


def test_inverted_range_returns_empty():
    out = dates_due(RecurrenceType.DAILY, None, date(2026, 4, 20), date(2026, 4, 19))
    assert out == []


def test_dst_spring_forward_us_eastern_does_not_skip_a_date():
    """DST transitions shift clock time, not calendar dates — a daily rule
    should still return exactly one entry per calendar day across a spring
    forward. (Our engine is date-only so this is really a reminder: don't
    accidentally introduce datetime arithmetic here.)
    """
    # 2025-03-09 is the US spring forward.
    out = dates_due(RecurrenceType.DAILY, None, date(2025, 3, 8), date(2025, 3, 10))
    assert out == [date(2025, 3, 8), date(2025, 3, 9), date(2025, 3, 10)]


def test_dst_fall_back_us_eastern_does_not_duplicate_a_date():
    # 2025-11-02 is the US fall back.
    out = dates_due(RecurrenceType.DAILY, None, date(2025, 11, 1), date(2025, 11, 3))
    assert out == [date(2025, 11, 1), date(2025, 11, 2), date(2025, 11, 3)]


@pytest.mark.parametrize("rt", list(RecurrenceType))
def test_every_rule_type_has_branch(rt):
    # Exhaustive coverage check: no rule type should silently fall through.
    cfg = {
        RecurrenceType.SPECIFIC_DAYS: {"days": [1]},
        RecurrenceType.EVERY_N_DAYS: {"n": 1, "anchor": "2026-01-01"},
        RecurrenceType.MONTHLY_ON_DATE: {"day": 1},
        RecurrenceType.ONCE: {"date": "2026-01-05"},
    }.get(rt, {})
    out = dates_due(rt, cfg, date(2026, 1, 1), date(2026, 1, 7))
    assert isinstance(out, list)
