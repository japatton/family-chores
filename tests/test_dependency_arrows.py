"""Architecture test: enforce that `packages/*` never imports `apps/*`.

This is the dependency-arrow guard called out in DECISIONS §11 Q4.

The Phase 2 refactor splits the monorepo into shared **packages/** and
deployment-target **apps/** (plus the add-on at `family_chores/`, which
is structurally an app). The arrow must always point apps → packages,
never the reverse — otherwise multi-tenancy plumbing in packages/api will
silently re-couple to add-on internals and the SaaS backend (Phase 3)
won't be a clean composition root.

What this test forbids inside `packages/*`:

  - `from family_chores.X import ...` / `import family_chores.X`
    (the add-on's package, also temporarily named `family_chores` until
    step 6's flatten when it becomes `family_chores_addon`).
  - `from family_chores_addon.* import ...` (post-step-6 name).
  - `from family_chores_saas.* import ...` (the saas scaffold).

What this test allows:

  - Cross-package imports between workspace packages
    (`family_chores_core`, `family_chores_db`, `family_chores_api`) —
    those are the legitimate apps → packages dependencies.

Tests at `family_chores/tests/`, `apps/saas-backend/tests/`, etc. are
NOT walked — they're allowed to import addon code freely (they ARE the
addon's tests).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_DIR = REPO_ROOT / "packages"

# Match `from family_chores.X` and `from family_chores_addon` /
# `family_chores_saas`, but NOT `family_chores_core` / `_db` / `_api`.
# The trailing class is `[._]` so we match either `family_chores.api` or a
# whole-word `family_chores` followed by EOL — but we DON'T match
# `family_chores_core`, where the trailing char is an underscore-letter
# part of the longer name.
_FORBIDDEN_PATTERNS = [
    # `from family_chores.X` or `from family_chores import ...` (with the
    # exact word `family_chores`, not `family_chores_core` etc.)
    re.compile(r"^\s*from\s+family_chores(\.[a-zA-Z_][\w.]*)?\s+import\s"),
    re.compile(r"^\s*import\s+family_chores(\.[a-zA-Z_][\w.]*)?\s*$"),
    re.compile(r"^\s*from\s+family_chores_addon(\.[a-zA-Z_][\w.]*)?\s+import\s"),
    re.compile(r"^\s*import\s+family_chores_addon(\.[a-zA-Z_][\w.]*)?\s*$"),
    re.compile(r"^\s*from\s+family_chores_saas(\.[a-zA-Z_][\w.]*)?\s+import\s"),
    re.compile(r"^\s*import\s+family_chores_saas(\.[a-zA-Z_][\w.]*)?\s*$"),
]


def _python_files(root: Path):
    """Yield every .py file under root, skipping caches and build output."""
    skip_parts = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "build", "dist"}
    for path in root.rglob("*.py"):
        if any(part in skip_parts for part in path.parts):
            continue
        yield path


@pytest.mark.parametrize("py_file", list(_python_files(PACKAGES_DIR)), ids=str)
def test_packages_have_no_apps_imports(py_file: Path) -> None:
    """Every line in every packages/* .py file must avoid apps-side imports."""
    text = py_file.read_text(encoding="utf-8")
    violations: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.match(line):
                violations.append(f"  line {line_no}: {line.strip()}")
                break
    if violations:
        rel = py_file.relative_to(REPO_ROOT)
        msg = (
            f"\n{rel} imports from an apps-side module — this would couple "
            f"a shared package to a deployment target.\n"
            "Permitted workspace packages: family_chores_core, family_chores_db, "
            "family_chores_api.\n"
            "Forbidden: family_chores (the addon, until step 6), "
            "family_chores_addon, family_chores_saas.\n"
            "\nViolations:\n" + "\n".join(violations)
        )
        raise AssertionError(msg)
