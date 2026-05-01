"""Prep-text parsing for calendar events (DECISIONS §14).

Two passes feed a single `list[PrepItem]` output:

  1. **Explicit tag (power-user path):** `[prep: cleats, water bottle, $5]`
     anywhere in the event description. Wins over verb detection — a
     parent who tagged means business.

  2. **Verb fallback (80% case):** look for sentence-anchored
     `bring|wear|pack|don't forget` (the 4-phrase / 5-word list from
     DECISIONS §14 Q3) and capture the noun phrase that follows up to
     the next sentence terminator.

Either pass splits multi-item phrases on commas and ` and ` so
"cleats, water bottle" and "cleats and water bottle" both produce
two items.

A small icon dictionary maps common kid items to emoji (cleats → 🥾,
water bottle → 💧, etc.) so the UI can render chips with visual
shorthand. Unknown items have `icon=None` and render text-only.

Pure module: no I/O, no DB, no logging. Easy to test in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PrepItem:
    """A single thing the kid needs to bring/wear/pack for an event.

    `label` is the parent's wording, normalised (whitespace-trimmed,
    trailing punctuation stripped). `icon` is an emoji from the
    built-in dictionary, or None if no match — the UI renders text-only
    in that case.
    """

    label: str
    icon: str | None = None


# Power-user explicit tag. Captures everything between `[prep:` and `]`.
# Case-insensitive on the keyword so `[Prep: ...]` also works.
_PREP_TAG_RE = re.compile(r"\[prep:\s*([^\]]+)\]", re.IGNORECASE)


# Verb-fallback patterns. Each captures the noun phrase that follows the
# verb, up to the next sentence terminator (. ! ? or newline). Word
# boundaries (\b) match the verb anywhere — sentence-initial isn't
# required because parents often write things like
# "Reminder: don't forget X".
_VERB_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bbring\s+([^.!?\n]+)", re.IGNORECASE),
    re.compile(r"\bwear\s+([^.!?\n]+)", re.IGNORECASE),
    re.compile(r"\bpack\s+([^.!?\n]+)", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+forget\s+([^.!?\n]+)", re.IGNORECASE),
)


# Common kid items → emoji. Conservative — covers the high-traffic items
# (sports, school, weather) without drifting into a brittle 200-entry
# dictionary. Add entries as real families surface gaps.
_ICON_DICT: dict[str, str] = {
    "backpack": "🎒",
    "ball": "⚽",
    "basketball": "🏀",
    "book": "📚",
    "books": "📚",
    "cash": "💵",
    "cleats": "🥾",
    "gloves": "🧤",
    "hat": "🧢",
    "homework": "📝",
    "instrument": "🎵",
    "jacket": "🧥",
    "lunch": "🍱",
    "money": "💵",
    "permission slip": "📄",
    "shoes": "👟",
    "snack": "🍎",
    "snacks": "🍎",
    "soccer ball": "⚽",
    "sunscreen": "🧴",
    "swimsuit": "🩱",
    "towel": "🏖️",
    "umbrella": "☂️",
    "violin": "🎻",
    "water": "💧",
    "water bottle": "💧",
}


# Strip leading possessives and trailing punctuation so "your lunch"
# normalises to "lunch" and "lunch." normalises to "lunch". Conservative
# — only the most common cases.
_LEADING_POSSESSIVES = re.compile(r"^(?:your|the|a|an)\s+", re.IGNORECASE)
_TRAILING_PUNCTUATION = re.compile(r"[.,;:!?]+$")

# Truncate verb-captured noun phrases at the first prepositional clause.
# Real-world: "Bring water bottle to practice" → prep item is just
# "water bottle", not "water bottle to practice". The explicit `[prep:]`
# tag bypasses this truncation (it splits on commas / `and` only) so a
# parent who wants the full phrase can override.
_CLAUSE_BREAK = re.compile(
    r"\s+(?:to|for|at|on|in|by|with|from|of|before|after|until|because)\s+",
    re.IGNORECASE,
)


def _normalize_label(raw: str) -> str:
    """Trim, strip leading possessives, strip trailing punctuation."""
    s = raw.strip()
    s = _LEADING_POSSESSIVES.sub("", s)
    s = _TRAILING_PUNCTUATION.sub("", s)
    # Collapse internal whitespace so "lunch  bag" matches "lunch bag".
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _split_items(raw: str) -> list[str]:
    """Split a noun-phrase blob into individual items.

    Splits on commas first, then on ` and ` between phrases. Each part
    is normalised; empty parts dropped.
    """
    parts: list[str] = []
    for chunk in raw.split(","):
        for sub in re.split(r"\s+and\s+", chunk, flags=re.IGNORECASE):
            normalized = _normalize_label(sub)
            if normalized:
                parts.append(normalized)
    return parts


def _icon_for(label: str) -> str | None:
    """Look up an emoji for a normalised label.

    Tries the full lowercased label first (so "water bottle" hits the
    multi-word entry), then falls back to any single word that matches
    (so "spare water bottle" still gets 💧 via the "water bottle" or
    "water" entries).
    """
    lc = label.lower().strip()
    if not lc:
        return None
    if lc in _ICON_DICT:
        return _ICON_DICT[lc]
    # Multi-word fallback: try progressively shorter suffixes for
    # compound entries like "water bottle".
    words = lc.split()
    for i in range(len(words)):
        candidate = " ".join(words[i:])
        if candidate in _ICON_DICT:
            return _ICON_DICT[candidate]
    # Single-word fallback: any word matches.
    for word in words:
        if word in _ICON_DICT:
            return _ICON_DICT[word]
    return None


def extract_prep_items(description: str | None) -> list[PrepItem]:
    """Extract prep items from an event description.

    Returns an empty list for None / empty / no-match input. Order
    follows the source text (so the parent's intended sequence is
    preserved on the kid's tile).
    """
    if not description:
        return []

    # Explicit-tag pass wins.
    tag_match = _PREP_TAG_RE.search(description)
    if tag_match:
        return [
            PrepItem(label=label, icon=_icon_for(label))
            for label in _split_items(tag_match.group(1))
        ]

    # Verb fallback. Multiple verb hits each contribute; dedupe by
    # normalised label so "Bring lunch. Don't forget lunch." doesn't
    # double up. Truncate at clause breaks so "Bring water bottle to
    # practice" yields "water bottle" not "water bottle to practice".
    seen: set[str] = set()
    items: list[PrepItem] = []
    for pattern in _VERB_PATTERNS:
        for match in pattern.finditer(description):
            captured = _CLAUSE_BREAK.split(match.group(1), maxsplit=1)[0]
            for label in _split_items(captured):
                key = label.lower()
                if key in seen:
                    continue
                seen.add(key)
                items.append(PrepItem(label=label, icon=_icon_for(label)))
    return items
