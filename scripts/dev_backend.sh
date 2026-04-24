#!/bin/sh
# Run the backend locally, outside HA, with a tmp data dir and no scheduler.
#
# Updated in Phase 2 step 6 + step 12 for the monorepo layout:
#   - Module is `family_chores_addon` (was `family_chores`).
#   - Started via `uv run` against the workspace.
#   - Default data dir is `local-data/` at the repo root, but
#     FAMILY_CHORES_DATA_DIR env override still works.
set -eu

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

: "${FAMILY_CHORES_DATA_DIR:=${ROOT}/local-data}"
mkdir -p "${FAMILY_CHORES_DATA_DIR}" "${FAMILY_CHORES_DATA_DIR}/avatars"
export FAMILY_CHORES_DATA_DIR

# Re-running against the real HA instance? Export HA_URL + HA_TOKEN.
# Otherwise the bridge installs a NoOpBridge and the app runs offline-only.

if ! command -v uv >/dev/null 2>&1; then
    echo "uv not found. Install with: brew install uv  (or see https://docs.astral.sh/uv/)"
    exit 1
fi

# `--all-packages` ensures every workspace dep is editable-installed in
# the .venv before running. Idempotent + fast on a warm cache.
uv sync --all-packages --extra dev >/dev/null

exec uv run python -m family_chores_addon
