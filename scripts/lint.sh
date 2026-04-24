#!/bin/sh
# Run the full local lint / test suite. Mirrors `.github/workflows/ci.yml`
# so a clean `scripts/lint.sh` means green CI.
#
# Updated in Phase 2 step 12 (DECISIONS §11) for the monorepo layout:
#   - Python tooling now runs via `uv` instead of a hand-rolled venv.
#   - Frontend tooling runs via pnpm (`pnpm --filter <pkg> ...`).
#   - Tests are split per workspace member (core/db/api/addon/saas) +
#     the workspace-root architecture tests (dep-arrows + packages-clean).
set -eu

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Install with: brew install uv  (or see https://docs.astral.sh/uv/)"
    exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
    echo "pnpm not found. Activate via: corepack enable && corepack prepare pnpm@9.15.0 --activate"
    exit 1
fi

echo "── uv sync (workspace + dev extras) ──"
uv sync --all-packages --extra dev >/dev/null

echo "── ruff check (whole workspace) ──"
uv run ruff check \
    packages \
    family_chores/src family_chores/tests \
    apps/saas-backend/src apps/saas-backend/tests \
    tests

echo "── addon mypy --strict ──"
(cd family_chores && uv run mypy src --strict)

echo "── pytest core ──"
uv run pytest packages/core/tests -q

echo "── pytest db ──"
uv run pytest packages/db/tests -q

echo "── pytest api ──"
uv run pytest packages/api/tests -q

echo "── pytest addon ──"
uv run pytest family_chores/tests -q

echo "── pytest saas ──"
uv run pytest apps/saas-backend/tests -q

echo "── pytest architecture (dep-arrows + packages-clean) ──"
uv run pytest tests -q

echo "── pnpm install (workspace) ──"
pnpm install --frozen-lockfile >/dev/null

echo "── frontend (addon) lint + typecheck + vitest ──"
(cd family_chores/frontend && pnpm run lint && pnpm run typecheck && pnpm test)

echo "── frontend (web) typecheck (via build) + vitest ──"
(cd apps/web && pnpm run build >/dev/null && pnpm test)

echo "── lovelace-card typecheck ──"
(cd lovelace-card && pnpm run typecheck)

echo
echo "All checks passed."
