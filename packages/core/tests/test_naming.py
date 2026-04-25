"""Tests for `normalize_chore_name`.

This is the canonical dedup key for `chore_template.name_normalized`.
The (household_id, name_normalized) uniqueness constraint depends on
its idempotency and stability — anything that breaks the invariants
here will surface as duplicate-template bugs in the seeder.
"""

from __future__ import annotations

from family_chores_core.naming import normalize_chore_name


# ─── basic transformations ────────────────────────────────────────────────


def test_lowercases_uppercase() -> None:
    assert normalize_chore_name("Make Bed") == "make bed"


def test_strip_trailing_period() -> None:
    assert normalize_chore_name("Make bed.") == "make bed"


def test_strip_trailing_exclamation() -> None:
    assert normalize_chore_name("DONE!") == "done"


def test_strip_leading_trailing_whitespace() -> None:
    assert normalize_chore_name("  make bed  ") == "make bed"


def test_collapse_internal_whitespace() -> None:
    assert normalize_chore_name("make  bed") == "make bed"


def test_collapse_internal_tabs_and_newlines() -> None:
    assert normalize_chore_name("make\tbed\n") == "make bed"


def test_collapse_unicode_whitespace() -> None:
    """Non-breaking space (U+00A0) and similar should collapse like ASCII space."""
    assert normalize_chore_name("make\u00a0bed") == "make bed"


# ─── preservation ─────────────────────────────────────────────────────────


def test_preserves_emoji() -> None:
    assert normalize_chore_name("🛏 Make bed") == "🛏 make bed"


def test_preserves_emoji_at_end() -> None:
    """Emoji are not in our trailing-punctuation set — keep them."""
    assert normalize_chore_name("Take out trash 🗑") == "take out trash 🗑"


def test_preserves_accented_chars() -> None:
    """Spanish 'baño' must keep the ñ; case-folding lowercases it Unicode-aware."""
    assert normalize_chore_name("Limpiar Baño") == "limpiar baño"


def test_does_not_strip_punctuation_in_middle() -> None:
    """A parent might genuinely want 'feed cat (am)' and 'feed cat (pm)'
    as distinct chores. Mid-string punctuation must not be touched."""
    assert normalize_chore_name("feed cat (am)") == "feed cat (am)"
    assert normalize_chore_name("clean fridge/freezer") == "clean fridge/freezer"


# ─── idempotency ──────────────────────────────────────────────────────────


def test_idempotent_on_messy_input() -> None:
    messy = "  Make  Bed!! "
    once = normalize_chore_name(messy)
    twice = normalize_chore_name(once)
    assert once == twice == "make bed"


def test_idempotent_on_clean_input() -> None:
    """A pre-normalized name is unchanged by another pass."""
    clean = "tidy bedroom"
    assert normalize_chore_name(clean) == clean


# ─── edge cases ───────────────────────────────────────────────────────────


def test_empty_returns_empty() -> None:
    assert normalize_chore_name("") == ""


def test_whitespace_only_returns_empty() -> None:
    assert normalize_chore_name("   \t  \n") == ""


def test_punctuation_only_returns_empty() -> None:
    """All-punctuation reduces to empty, then short-circuits — no crash."""
    assert normalize_chore_name("!!!") == ""
    assert normalize_chore_name("...") == ""


def test_strips_multiple_trailing_punctuation() -> None:
    """`rstrip(charset)` already handles the `'foo!!!'` case in one call."""
    assert normalize_chore_name("Make bed!!!") == "make bed"
    assert normalize_chore_name("really?!") == "really"


def test_strips_trailing_punct_then_whitespace() -> None:
    """`'Make bed .'` (with space before the dot) — strip dot then space."""
    assert normalize_chore_name("Make bed .") == "make bed"
    assert normalize_chore_name("Make bed . ") == "make bed"


# ─── dedup invariant ──────────────────────────────────────────────────────


def test_dedup_equivalence_across_surface_forms() -> None:
    """The whole point — different-looking names reduce to the same key."""
    canonical = normalize_chore_name("Make Bed")
    variants = [
        "make bed",
        "Make bed.",
        " MAKE BED ",
        "Make  Bed",
        "make bed!",
        "make bed?",
        "make bed!!",
        "  make\tbed  ",
    ]
    for v in variants:
        assert normalize_chore_name(v) == canonical, (
            f"variant {v!r} did not normalize to {canonical!r}"
        )
