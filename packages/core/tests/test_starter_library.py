"""Validation tests for the bundled starter chore library.

Two layers:

  - Tests against the real bundled JSON file — assert what the shipped
    library promises (count, unique keys, valid categories/icons/recurrence,
    age-bound consistency).
  - Tests against synthetic payloads via `parse_starter_library()` —
    exercise the schema-error paths the loader needs to handle when the
    JSON file drifts.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from family_chores_core.enums import ChoreCategory, RecurrenceType
from family_chores_core.starter_library import (
    StarterLibraryError,
    library_recurrence_to_engine,
    load_starter_library,
    parse_starter_library,
)

EXPECTED_COUNT = 46


# ─── library content tests (against the real bundled JSON) ────────────────


def test_loads_without_error() -> None:
    lib = load_starter_library()
    assert lib.version >= 1
    assert lib.updated  # non-empty ISO date string


def test_count_is_46() -> None:
    """Per DECISIONS §13 — the curated set is 46 chores spanning ages 3–10+."""
    lib = load_starter_library()
    assert len(lib.chores) == EXPECTED_COUNT


def test_keys_unique() -> None:
    lib = load_starter_library()
    keys = [c.key for c in lib.chores]
    assert len(set(keys)) == len(keys), "duplicate starter_key in library"


def test_every_category_canonical() -> None:
    lib = load_starter_library()
    valid = {c.value for c in ChoreCategory}
    for entry in lib.chores:
        assert entry.category in valid, (
            f"{entry.key}: category {entry.category!r} not in canonical set"
        )


def test_every_icon_uses_mdi_prefix() -> None:
    lib = load_starter_library()
    for entry in lib.chores:
        assert entry.icon.startswith("mdi:"), entry.key
        assert len(entry.icon) > len("mdi:"), entry.key


def test_every_recurrence_translates_to_engine() -> None:
    """Every library entry's `default_recurrence` label must map to a
    real `RecurrenceType` and a config dict the engine accepts."""
    lib = load_starter_library()
    for entry in lib.chores:
        rt, cfg = library_recurrence_to_engine(entry.default_recurrence)
        assert isinstance(rt, RecurrenceType), entry.key
        assert isinstance(cfg, dict), entry.key


def test_age_min_max_consistency() -> None:
    """When both bounds are set, max >= min."""
    lib = load_starter_library()
    for entry in lib.chores:
        if entry.age_min is not None and entry.age_max is not None:
            assert entry.age_max >= entry.age_min, entry.key


def test_points_suggested_nonneg() -> None:
    lib = load_starter_library()
    for entry in lib.chores:
        assert entry.points_suggested >= 0, entry.key


def test_every_category_has_at_least_one_entry() -> None:
    """No empty categories — keeps the Browse Suggestions panel from
    showing an empty group."""
    lib = load_starter_library()
    used = {c.category for c in lib.chores}
    expected = {c.value for c in ChoreCategory}
    assert used == expected, f"unused categories: {expected - used}"


# ─── recurrence translation tests ─────────────────────────────────────────


def test_weekly_translates_to_specific_days_saturday() -> None:
    """DECISIONS §13 Q1 — 'weekly' library entries map to SPECIFIC_DAYS
    with Saturday (ISO 6) as the default day."""
    rt, cfg = library_recurrence_to_engine("weekly")
    assert rt is RecurrenceType.SPECIFIC_DAYS
    assert cfg == {"days": [6]}


def test_daily_translates_to_daily() -> None:
    rt, cfg = library_recurrence_to_engine("daily")
    assert rt is RecurrenceType.DAILY
    assert cfg == {}


def test_unknown_recurrence_label_raises() -> None:
    with pytest.raises(StarterLibraryError):
        library_recurrence_to_engine("yearly")


def test_recurrence_translation_returns_fresh_config() -> None:
    """Caller-mutating the returned dict must not poison the next call."""
    _, cfg1 = library_recurrence_to_engine("weekly")
    cfg1["days"].append(99)
    _, cfg2 = library_recurrence_to_engine("weekly")
    assert cfg2 == {"days": [6]}, "translation table got mutated"


# ─── parser error-path tests (synthetic payloads) ─────────────────────────


def _good_entry() -> dict[str, Any]:
    return {
        "key": "test_chore",
        "name": "Test chore",
        "icon": "mdi:bed-empty",
        "category": "bedroom",
        "age_min": 4,
        "age_max": None,
        "points_suggested": 2,
        "default_recurrence": "daily",
        "description": "Test description.",
    }


def _good_library(entry: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "updated": "2026-04-25",
        "chores": [entry if entry is not None else _good_entry()],
    }


def test_parse_accepts_minimal_well_formed_library() -> None:
    lib = parse_starter_library(_good_library())
    assert lib.version == 1
    assert len(lib.chores) == 1
    assert lib.chores[0].key == "test_chore"


def test_parse_rejects_non_object_root() -> None:
    with pytest.raises(StarterLibraryError, match="root"):
        parse_starter_library([])


def test_parse_rejects_missing_version() -> None:
    raw = _good_library()
    del raw["version"]
    with pytest.raises(StarterLibraryError, match="'version'"):
        parse_starter_library(raw)


def test_parse_rejects_invalid_category() -> None:
    entry = _good_entry()
    entry["category"] = "not_a_category"
    with pytest.raises(StarterLibraryError, match="category"):
        parse_starter_library(_good_library(entry))


def test_parse_rejects_non_mdi_icon() -> None:
    entry = _good_entry()
    entry["icon"] = "fa:home"
    with pytest.raises(StarterLibraryError, match="mdi:"):
        parse_starter_library(_good_library(entry))


def test_parse_rejects_empty_icon_after_prefix() -> None:
    entry = _good_entry()
    entry["icon"] = "mdi:"
    with pytest.raises(StarterLibraryError, match="mdi:"):
        parse_starter_library(_good_library(entry))


def test_parse_rejects_negative_points() -> None:
    entry = _good_entry()
    entry["points_suggested"] = -1
    with pytest.raises(StarterLibraryError, match="points_suggested"):
        parse_starter_library(_good_library(entry))


def test_parse_rejects_bool_for_points() -> None:
    """`bool` is `int` in Python — guard against `True`/`False` slipping in
    as 1/0."""
    entry = _good_entry()
    entry["points_suggested"] = True
    with pytest.raises(StarterLibraryError, match="points_suggested"):
        parse_starter_library(_good_library(entry))


def test_parse_rejects_unknown_recurrence_label() -> None:
    entry = _good_entry()
    entry["default_recurrence"] = "every_full_moon"
    with pytest.raises(StarterLibraryError, match="default_recurrence"):
        parse_starter_library(_good_library(entry))


def test_parse_rejects_inverted_age_bounds() -> None:
    entry = _good_entry()
    entry["age_min"] = 10
    entry["age_max"] = 5
    with pytest.raises(StarterLibraryError, match="age_max"):
        parse_starter_library(_good_library(entry))


def test_parse_rejects_duplicate_keys() -> None:
    raw = _good_library()
    raw["chores"].append(deepcopy(raw["chores"][0]))
    with pytest.raises(StarterLibraryError, match="duplicate key"):
        parse_starter_library(raw)


def test_parse_rejects_missing_required_field() -> None:
    entry = _good_entry()
    del entry["name"]
    with pytest.raises(StarterLibraryError, match="'name'"):
        parse_starter_library(_good_library(entry))


def test_parse_error_message_includes_key_when_available() -> None:
    """Schema errors should name the offending entry by `key` so a real-world
    library typo is easy to find."""
    entry = _good_entry()
    entry["key"] = "broken_entry"
    entry["category"] = "not_a_category"
    with pytest.raises(StarterLibraryError, match="broken_entry"):
        parse_starter_library(_good_library(entry))
