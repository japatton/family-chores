"""Pure-unit tests for the calendar prep parser.

Lives in `packages/api/tests/` rather than alongside the addon because
the prep parser has no DB / framework deps and can run in isolation.
"""

from __future__ import annotations

import pytest

from family_chores_api.services.calendar.prep import PrepItem, extract_prep_items


# ─── empty / no-match input ──────────────────────────────────────────────


def test_returns_empty_for_none():
    assert extract_prep_items(None) == []


def test_returns_empty_for_empty_string():
    assert extract_prep_items("") == []


def test_returns_empty_when_no_tag_or_verb():
    assert extract_prep_items("Soccer practice at the field.") == []


# ─── explicit-tag pass ───────────────────────────────────────────────────


def test_explicit_tag_single_item():
    items = extract_prep_items("Soccer game [prep: cleats]")
    assert items == [PrepItem(label="cleats", icon="🥾")]


def test_explicit_tag_multi_item_comma():
    items = extract_prep_items("[prep: cleats, water bottle, snack]")
    assert items == [
        PrepItem(label="cleats", icon="🥾"),
        PrepItem(label="water bottle", icon="💧"),
        PrepItem(label="snack", icon="🍎"),
    ]


def test_explicit_tag_multi_item_and():
    items = extract_prep_items("[prep: cleats and water bottle]")
    assert [i.label for i in items] == ["cleats", "water bottle"]


def test_explicit_tag_case_insensitive():
    items = extract_prep_items("[Prep: lunch]")
    assert items == [PrepItem(label="lunch", icon="🍱")]


def test_explicit_tag_wins_over_verb_detection():
    """If a parent took the trouble to tag, ignore stray verbs."""
    items = extract_prep_items("[prep: cleats] Bring snacks for everyone")
    assert [i.label for i in items] == ["cleats"]


def test_explicit_tag_unknown_item_has_no_icon():
    items = extract_prep_items("[prep: rocketship parts]")
    # Neither "rocketship" nor "parts" is in the dict.
    assert items == [PrepItem(label="rocketship parts", icon=None)]


def test_explicit_tag_does_not_truncate_at_clause():
    """Explicit [prep:] respects the parent's exact wording. Verb
    fallback truncates at prepositions; explicit tag does not."""
    items = extract_prep_items("[prep: $5 for snacks]")
    assert items[0].label == "$5 for snacks"
    # "snacks" matches the dictionary via single-word fallback in _icon_for.
    assert items[0].icon == "🍎"


# ─── verb-fallback pass ──────────────────────────────────────────────────


def test_verb_bring():
    items = extract_prep_items("Bring cleats")
    assert items == [PrepItem(label="cleats", icon="🥾")]


def test_verb_wear():
    items = extract_prep_items("Wear uniform")
    assert [i.label for i in items] == ["uniform"]


def test_verb_pack():
    items = extract_prep_items("Pack lunch")
    assert items == [PrepItem(label="lunch", icon="🍱")]


def test_verb_dont_forget():
    items = extract_prep_items("Don't forget homework")
    assert items == [PrepItem(label="homework", icon="📝")]


def test_verb_dont_forget_apostrophe_optional():
    items = extract_prep_items("Dont forget homework")
    assert items == [PrepItem(label="homework", icon="📝")]


def test_verb_strips_leading_possessive():
    """'your lunch' should normalise to 'lunch' so the icon lookup hits."""
    items = extract_prep_items("Don't forget your lunch")
    assert items == [PrepItem(label="lunch", icon="🍱")]


def test_verb_captures_until_sentence_end():
    items = extract_prep_items("Wear uniform. Practice starts at 4.")
    assert [i.label for i in items] == ["uniform"]


def test_verb_multiple_in_one_description():
    items = extract_prep_items("Wear uniform. Pack lunch. Don't forget cleats.")
    assert [i.label for i in items] == ["uniform", "lunch", "cleats"]


def test_verb_dedup_across_patterns():
    """Same item mentioned twice via different verbs collapses to one."""
    items = extract_prep_items("Bring lunch. Don't forget lunch!")
    assert items == [PrepItem(label="lunch", icon="🍱")]


def test_verb_compound_split_on_and():
    items = extract_prep_items("Bring cleats and water bottle")
    assert [i.label for i in items] == ["cleats", "water bottle"]


def test_verb_anywhere_not_just_sentence_start():
    """Word boundary on the verb means it matches mid-sentence too.
    The clause-break truncation drops the trailing "to practice" too."""
    items = extract_prep_items("Reminder: bring water bottle to practice")
    assert [i.label for i in items] == ["water bottle"]


def test_verb_truncates_at_clause_break():
    """Verb-captured noun phrase stops at common prepositions so
    "Bring lunch to school" yields "lunch" not "lunch to school"."""
    items = extract_prep_items("Bring lunch to school")
    assert items == [PrepItem(label="lunch", icon="🍱")]


def test_verb_strips_trailing_punctuation():
    items = extract_prep_items("Bring cleats!")
    assert items == [PrepItem(label="cleats", icon="🥾")]


# ─── icon dictionary ─────────────────────────────────────────────────────


def test_icon_compound_lookup_prefers_full_match():
    """'water bottle' should hit 💧 via the multi-word entry, not as
    a single word fallback."""
    items = extract_prep_items("[prep: water bottle]")
    assert items == [PrepItem(label="water bottle", icon="💧")]


def test_icon_unknown_item_has_no_icon():
    items = extract_prep_items("[prep: rocketship]")
    assert items == [PrepItem(label="rocketship", icon=None)]


def test_icon_compound_with_extra_words_falls_back():
    """'spare water bottle' tries full match (miss), then 'water bottle'
    (hit). Verifies the suffix-fallback in _icon_for."""
    items = extract_prep_items("[prep: spare water bottle]")
    assert items == [PrepItem(label="spare water bottle", icon="💧")]


# ─── ordering ────────────────────────────────────────────────────────────


def test_order_preserved_within_tag():
    items = extract_prep_items("[prep: c, a, b]")
    assert [i.label for i in items] == ["c", "a", "b"]


def test_all_verbs_in_one_description():
    """All four verb patterns each contribute. Labels preserve the
    parent's casing (uppercase here)."""
    items = extract_prep_items("Wear A. Bring B. Pack C. Don't forget D.")
    assert {i.label for i in items} == {"A", "B", "C", "D"}


# ─── empty-input edge cases ──────────────────────────────────────────────


def test_empty_tag_returns_empty():
    assert extract_prep_items("[prep: ]") == []


def test_whitespace_only_tag_returns_empty():
    assert extract_prep_items("[prep:    ]") == []


@pytest.mark.parametrize("text", ["bring  ", "wear", "pack."])
def test_verb_with_no_following_noun_returns_empty(text):
    """A bare verb with no noun phrase shouldn't produce a phantom item."""
    assert extract_prep_items(text) == []
