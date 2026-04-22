#!/bin/sh
# Run the backend locally, outside HA, with a tmp data dir and no scheduler.
set -eu

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

: "${FAMILY_CHORES_DATA_DIR:=${ROOT}/local-data}"
mkdir -p "${FAMILY_CHORES_DATA_DIR}" "${FAMILY_CHORES_DATA_DIR}/avatars"
export FAMILY_CHORES_DATA_DIR

# Re-running against the real HA instance? Export HA_URL + HA_TOKEN.
# Otherwise the bridge installs a NoOpBridge and the app runs offline-only.

if [ ! -d "${ROOT}/.venv" ]; then
    echo "No .venv found. Create one first:"
    echo "  python3 -m venv .venv && .venv/bin/pip install -e 'backend/[dev]'"
    exit 1
fi

cd "${ROOT}/backend"
exec "${ROOT}/.venv/bin/python" -m family_chores
