#!/bin/sh
# Placeholder wrapper that will grow to run ruff + mypy + tsc + eslint in
# milestone 8. For now it's enough to typecheck the two TypeScript surfaces.
set -eu

cd "$(dirname "$0")/.."

echo "── frontend typecheck ──"
(cd frontend && npm run typecheck)

echo "── backend pytest ──"
./.venv/bin/python -m pytest backend/tests/ -q
