"""Bundled starter library of age-appropriate chore templates.

The library is a version-controlled JSON file under `data/`. This module
loads, validates, and exposes it as immutable Python objects. Nothing
here writes to a database — the seeder in
`family_chores_api.services.starter_seeding` consumes
`load_starter_library()` and creates `chore_template` rows.

The library uses two friendly recurrence labels — `"daily"` and `"weekly"` —
that translate to engine-canonical `(RecurrenceType, config)` pairs via
`library_recurrence_to_engine()`. The JSON stays human-readable as a
catalogue; the engine never sees the friendly labels. Saturday is the
default day for `"weekly"` per DECISIONS §13 Q1.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from importlib import resources
from typing import Any, Final

from family_chores_core.enums import ChoreCategory, RecurrenceType

_LIBRARY_PACKAGE: Final[str] = "family_chores_core.data"
_LIBRARY_FILENAME: Final[str] = "starter_library.json"

# Library JSON uses "daily" and "weekly" as friendly labels; the engine
# uses RecurrenceType. Saturday is the default weekly day per DECISIONS §13
# Q1 — a sensible neutral default that maps onto SPECIFIC_DAYS without
# requiring the parent to pick one before saving.
_LIBRARY_RECURRENCE_TRANSLATIONS: Final[
    Mapping[str, tuple[RecurrenceType, dict[str, Any]]]
] = {
    "daily": (RecurrenceType.DAILY, {}),
    "weekly": (RecurrenceType.SPECIFIC_DAYS, {"days": [6]}),
}

# Canonical category set duplicated as a frozenset for O(1) membership
# checks during loading. Kept in sync with `ChoreCategory` via
# `_CATEGORY_VALUES` below — the test suite asserts they match.
_CATEGORY_VALUES: Final[frozenset[str]] = frozenset(c.value for c in ChoreCategory)


class StarterLibraryError(ValueError):
    """Raised on schema validation failure during library load."""


@dataclass(frozen=True, slots=True)
class StarterLibraryEntry:
    """One starter-library chore. Immutable; safe to share across requests."""

    key: str
    name: str
    icon: str
    category: str
    age_min: int | None
    age_max: int | None
    points_suggested: int
    default_recurrence: str  # library label; translate via library_recurrence_to_engine()
    description: str | None


@dataclass(frozen=True, slots=True)
class StarterLibrary:
    """Top-level container for the bundled starter library."""

    version: int
    updated: str  # ISO date string, e.g. "2026-04-25"
    chores: tuple[StarterLibraryEntry, ...]


def library_recurrence_to_engine(label: str) -> tuple[RecurrenceType, dict[str, Any]]:
    """Translate a library recurrence label to `(RecurrenceType, fresh config dict)`.

    Returns a deep copy on every call so the seeder can mutate the
    returned config (or persist it to the DB and have it later mutated
    by ORM hydration) without aliasing the table-level template stored
    in `_LIBRARY_RECURRENCE_TRANSLATIONS`.

    `dict(cfg)` would NOT be enough — the SPECIFIC_DAYS payload contains
    a nested list which the shallow copy would still share.
    """
    try:
        rt, cfg = _LIBRARY_RECURRENCE_TRANSLATIONS[label]
    except KeyError as exc:
        raise StarterLibraryError(
            f"unknown library recurrence label {label!r}; "
            f"valid: {sorted(_LIBRARY_RECURRENCE_TRANSLATIONS)}"
        ) from exc
    return rt, deepcopy(cfg)


def load_starter_library() -> StarterLibrary:
    """Read the bundled JSON and return a validated `StarterLibrary`.

    Raises `StarterLibraryError` on any schema problem — broken data
    files surface loudly at startup rather than silently producing
    garbage templates.
    """
    text = (
        resources.files(_LIBRARY_PACKAGE)
        .joinpath(_LIBRARY_FILENAME)
        .read_text(encoding="utf-8")
    )
    return parse_starter_library(json.loads(text))


def parse_starter_library(raw: object) -> StarterLibrary:
    """Validate a pre-loaded JSON object and return a `StarterLibrary`.

    Split out from `load_starter_library` so unit tests can exercise the
    schema validator on synthetic payloads without writing to disk.
    """
    if not isinstance(raw, dict):
        raise StarterLibraryError("library root must be a JSON object")

    try:
        version = int(raw["version"])
    except KeyError as exc:
        raise StarterLibraryError("missing top-level field: 'version'") from exc
    except (TypeError, ValueError) as exc:
        raise StarterLibraryError("'version' must be an integer") from exc

    try:
        updated = str(raw["updated"])
    except KeyError as exc:
        raise StarterLibraryError("missing top-level field: 'updated'") from exc

    try:
        chores_raw = raw["chores"]
    except KeyError as exc:
        raise StarterLibraryError("missing top-level field: 'chores'") from exc

    if not isinstance(chores_raw, list):
        raise StarterLibraryError("'chores' must be a list")

    seen_keys: set[str] = set()
    entries: list[StarterLibraryEntry] = []
    for index, entry_raw in enumerate(chores_raw):
        entry = _parse_entry(entry_raw, index)
        if entry.key in seen_keys:
            raise StarterLibraryError(f"duplicate key {entry.key!r}")
        seen_keys.add(entry.key)
        entries.append(entry)

    return StarterLibrary(version=version, updated=updated, chores=tuple(entries))


def _parse_entry(raw: object, index: int) -> StarterLibraryEntry:
    if not isinstance(raw, dict):
        raise StarterLibraryError(f"chores[{index}] must be a JSON object")

    where = f"chores[{index}]"
    key_value = raw.get("key")
    if isinstance(key_value, str) and key_value:
        where = f"chores[{index}] (key={key_value!r})"

    required = (
        "key",
        "name",
        "icon",
        "category",
        "points_suggested",
        "default_recurrence",
    )
    for field in required:
        if field not in raw:
            raise StarterLibraryError(f"{where}: missing field {field!r}")

    if not isinstance(raw["key"], str) or not raw["key"]:
        raise StarterLibraryError(f"{where}: 'key' must be a non-empty string")

    if not isinstance(raw["name"], str) or not raw["name"].strip():
        raise StarterLibraryError(f"{where}: 'name' must be a non-empty string")

    icon = raw["icon"]
    if not isinstance(icon, str) or not icon.startswith("mdi:") or len(icon) <= 4:
        raise StarterLibraryError(
            f"{where}: 'icon' must be a non-empty string starting with 'mdi:'"
        )

    category = raw["category"]
    if category not in _CATEGORY_VALUES:
        raise StarterLibraryError(
            f"{where}: 'category' {category!r} not in canonical set "
            f"({sorted(_CATEGORY_VALUES)})"
        )

    points = raw["points_suggested"]
    if not isinstance(points, int) or isinstance(points, bool) or points < 0:
        # `bool` is an `int` subclass in Python — explicit guard so
        # `True`/`False` don't sneak through as 1/0.
        raise StarterLibraryError(
            f"{where}: 'points_suggested' must be a non-negative int"
        )

    default_recurrence = raw["default_recurrence"]
    if default_recurrence not in _LIBRARY_RECURRENCE_TRANSLATIONS:
        raise StarterLibraryError(
            f"{where}: 'default_recurrence' {default_recurrence!r} not in "
            f"library labels {sorted(_LIBRARY_RECURRENCE_TRANSLATIONS)}"
        )

    age_min = raw.get("age_min")
    age_max = raw.get("age_max")
    if age_min is not None and (not isinstance(age_min, int) or isinstance(age_min, bool)):
        raise StarterLibraryError(f"{where}: 'age_min' must be int or null")
    if age_max is not None and (not isinstance(age_max, int) or isinstance(age_max, bool)):
        raise StarterLibraryError(f"{where}: 'age_max' must be int or null")
    if age_min is not None and age_max is not None and age_max < age_min:
        raise StarterLibraryError(
            f"{where}: 'age_max' {age_max} is less than 'age_min' {age_min}"
        )

    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise StarterLibraryError(f"{where}: 'description' must be string or null")

    return StarterLibraryEntry(
        key=raw["key"],
        name=raw["name"],
        icon=icon,
        category=category,
        age_min=age_min,
        age_max=age_max,
        points_suggested=points,
        default_recurrence=default_recurrence,
        description=description,
    )
