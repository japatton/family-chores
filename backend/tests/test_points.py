"""Tests for the week-anchor + week-reset helpers."""

from __future__ import annotations

from datetime import date

import pytest

from family_chores.core.points import needs_week_reset, week_anchor_for


def test_week_anchor_monday_on_a_monday():
    # 2026-04-20 is a Monday
    assert week_anchor_for(date(2026, 4, 20), "monday") == date(2026, 4, 20)


def test_week_anchor_monday_on_a_wednesday():
    assert week_anchor_for(date(2026, 4, 22), "monday") == date(2026, 4, 20)


def test_week_anchor_monday_on_a_sunday():
    # Sunday 2026-04-26 belongs to the week starting Mon 2026-04-20
    assert week_anchor_for(date(2026, 4, 26), "monday") == date(2026, 4, 20)


def test_week_anchor_sunday_on_a_sunday():
    # Same 2026-04-26 Sunday, but with Sunday-start weeks anchors to itself.
    assert week_anchor_for(date(2026, 4, 26), "sunday") == date(2026, 4, 26)


def test_week_anchor_sunday_on_a_monday():
    # Monday 2026-04-20 belongs to the week that started Sunday 2026-04-19
    assert week_anchor_for(date(2026, 4, 20), "sunday") == date(2026, 4, 19)


def test_week_anchor_invalid_raises():
    with pytest.raises(ValueError):
        week_anchor_for(date(2026, 4, 20), "wednesday")


def test_needs_week_reset_no_stored_anchor():
    # First-ever login — reset must happen so we set the anchor.
    assert needs_week_reset(None, date(2026, 4, 22), "monday") is True


def test_needs_week_reset_same_week_is_false():
    # Stored anchor = this week's anchor → no reset
    assert needs_week_reset(date(2026, 4, 20), date(2026, 4, 22), "monday") is False


def test_needs_week_reset_different_week_is_true():
    # Stored anchor is last week's → reset
    assert needs_week_reset(date(2026, 4, 13), date(2026, 4, 22), "monday") is True


def test_needs_week_reset_is_idempotent_after_first_fire():
    # Fire once, update anchor, second call returns False — no double reset.
    today = date(2026, 4, 22)
    anchor = week_anchor_for(today, "monday")
    assert needs_week_reset(None, today, "monday") is True
    assert needs_week_reset(anchor, today, "monday") is False
