#!/bin/sh
# Run the full local lint / test suite. Mirrors `.github/workflows/ci.yml`
# so a clean `scripts/lint.sh` means green CI.
#
# Each Python tool is invoked with cwd=family_chores/backend so it picks
# up the [tool.mypy] / [tool.ruff] blocks in pyproject.toml. Running
# `mypy family_chores/backend/src` from the repo root silently ignores
# the config because mypy's discovery looks in cwd.
set -eu

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

VENV_PY="${ROOT}/.venv/bin/python"
if [ ! -x "${VENV_PY}" ]; then
    echo "No .venv found. Create one with:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -e 'family_chores/backend/[dev]'"
    exit 1
fi

echo "── backend ruff ──"
(cd family_chores/backend && "${ROOT}/.venv/bin/ruff" check .)

echo "── backend mypy --strict ──"
(cd family_chores/backend && "${ROOT}/.venv/bin/mypy" src --strict)

echo "── backend pytest ──"
(cd family_chores/backend && "${VENV_PY}" -m pytest tests/ -q)

echo "── frontend eslint ──"
(cd family_chores/frontend && npm run lint)

echo "── frontend typecheck ──"
(cd family_chores/frontend && npm run typecheck)

echo "── frontend vitest ──"
(cd family_chores/frontend && npm test)

echo "── card typecheck ──"
(cd lovelace-card && npm run typecheck)

echo
echo "All checks passed."
