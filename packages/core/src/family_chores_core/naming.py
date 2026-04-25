"""Chore-name normalization for dedup.

The seeder and the suggestions API both need a canonical form for chore
names so that `"Make bed"`, `"make bed."`, and `" Make  Bed "` all dedup
to the same `chore_template` row via the
`(household_id, name_normalized)` unique constraint.

`normalize_chore_name` is the single canonical function. Anything stored
in `chore_template.name_normalized` or compared against it MUST go
through this function — otherwise the dedup invariant breaks silently.

Idempotent by construction: `normalize_chore_name(normalize_chore_name(x))
== normalize_chore_name(x)` for every input.
"""

from __future__ import annotations

# Trailing characters that are pure sentence-ending punctuation. Kept
# deliberately conservative — stripping ALL punctuation (e.g. via
# `string.punctuation`) would mangle names with deliberate trailing
# tokens like `"feed cat (am)"` or `"clean fridge/freezer"`.
_TRAILING_PUNCTUATION = ".,;:!?…"


def normalize_chore_name(name: str) -> str:
    """Return the canonical dedup form of `name`.

    Steps (in order):

      1. Strip leading/trailing whitespace (any Unicode whitespace).
      2. Strip trailing sentence-ending punctuation (`.,;:!?…`),
         repeatedly — `"!!"` reduces all the way.
      3. Strip whitespace again (in case step 2 exposed trailing spaces
         from inputs like `"Make bed ."`).
      4. Collapse all internal whitespace runs (including tabs, newlines,
         non-breaking spaces) to single ASCII spaces.
      5. Lowercase via `str.lower()` (Unicode-aware — `"Ñ"` becomes `"ñ"`).

    Preserves emoji and accented characters — both can carry meaning for
    parents distinguishing otherwise-similar chores.

    Mid-string punctuation is left untouched. `"feed cat (am)"` stays
    `"feed cat (am)"`.

    Whitespace-only or empty input returns the empty string. The seeder
    and API layer must reject empty names at validation time — this
    function does not.
    """
    s = name.strip()
    if not s:
        return ""
    # `rstrip` already iterates so a single call handles `"!!!"`. The
    # second `rstrip()` cleans up whitespace exposed by punct removal.
    s = s.rstrip(_TRAILING_PUNCTUATION).rstrip()
    # `str.split()` with no args splits on every Unicode whitespace
    # codepoint and skips empty results, which collapses runs.
    s = " ".join(s.split())
    return s.lower()
