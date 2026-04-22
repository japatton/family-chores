#!/bin/sh
# Run the full local lint / test suite. Mirrors `.github/workflows/ci.yml`
# so a clean `scripts/lint.sh` means green CI.
set -eu

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

VENV_PY="${ROOT}/.venv/bin/python"
if [ ! -x "${VENV_PY}" ]; then
    echo "No .venv found. Create one with:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -e 'backend/[dev]'"
    exit 1
fi

echo "── backend ruff ──"
"${ROOT}/.venv/bin/ruff" check backend/

echo "── backend mypy --strict ──"
"${ROOT}/.venv/bin/mypy" backend/src --strict

echo "── backend pytest ──"
"${VENV_PY}" -m pytest backend/tests/ -q

echo "── frontend eslint ──"
(cd frontend && npm run lint)

echo "── frontend typecheck ──"
(cd frontend && npm run typecheck)

echo "── frontend vitest ──"
(cd frontend && npm test)

echo "── card typecheck ──"
(cd lovelace-card && npm run typecheck)

echo
echo "All checks passed."
