"""Architecture test: shared `packages/*` must not contain HA-specific strings.

This complements `test_dependency_arrows.py` (which catches addon-package
imports) by catching addon-specific *strings* — env-var names, header
names, and Supervisor terminology — that would silently leak the HA
deployment model into supposedly deployment-agnostic shared code.

Forbidden strings under `packages/api/src/` and `packages/core/src/`:
    - "supervisor"        — references HA Supervisor; the bridge is
                             responsible for talking to it, not the
                             routers/services.
    - "X-Ingress"         — HA-Ingress-injected header; identity should
                             go through `AuthStrategy`.
    - "X-Remote-User"     — same: Ingress-only header. Routers read
                             `Identity.user_key`.
    - "HA_TOKEN"          — addon env var for HA-Core long-lived token.
    - "SUPERVISOR_TOKEN"  — addon env var injected by Supervisor.

If a future change re-introduces any of these into a shared package,
this test fails with the file + the offending string.

`packages/db/src/` is excluded because its model column names (e.g.
`ha_todo_entity_id`) legitimately reference HA — those are persisted
data, not deployment-target plumbing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_FORBIDDEN = (
    "supervisor",
    "X-Ingress",
    "X-Remote-User",
    "HA_TOKEN",
    "SUPERVISOR_TOKEN",
)

_SCANNED_ROOTS = (
    REPO_ROOT / "packages" / "api" / "src",
    REPO_ROOT / "packages" / "core" / "src",
)


def _python_files() -> list[Path]:
    skip_parts = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    out: list[Path] = []
    for root in _SCANNED_ROOTS:
        for path in root.rglob("*.py"):
            if any(part in skip_parts for part in path.parts):
                continue
            out.append(path)
    return out


@pytest.mark.parametrize("py_file", _python_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_ha_specific_strings(py_file: Path) -> None:
    text = py_file.read_text(encoding="utf-8")
    # Match case-insensitively for "supervisor" (it's a word, not an env var
    # name). The other strings are exact symbols that should be matched
    # case-sensitively to avoid false positives in unrelated prose.
    lowered = text.lower()
    hits: list[str] = []
    if "supervisor" in lowered:
        hits.append("supervisor")
    for needle in _FORBIDDEN:
        if needle == "supervisor":
            continue
        if needle in text:
            hits.append(needle)
    if hits:
        rel = py_file.relative_to(REPO_ROOT)
        raise AssertionError(
            f"\n{rel} contains addon-specific string(s) that don't belong in a "
            f"shared package: {hits}.\n"
            "If this is a comment / docstring referring to the addon for "
            "context, paraphrase it. If it's actual code, the deployment-"
            "specific logic belongs in the addon (or in a SaaS-side strategy)."
        )
