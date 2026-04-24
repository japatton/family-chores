#!/bin/sh
# Vite dev server with /api proxied to the local backend on :8099.
#
# Updated in Phase 2 step 7 for the pnpm workspace migration:
#   - npm → pnpm via corepack (Node 22 ships it bundled).
#   - Workspace install ensures the lockfile is honoured.
set -eu

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

if ! command -v pnpm >/dev/null 2>&1; then
    echo "pnpm not found. Activate via: corepack enable && corepack prepare pnpm@9.15.0 --activate"
    exit 1
fi

# Workspace install (idempotent on a warm cache).
pnpm install --frozen-lockfile >/dev/null

cd "${ROOT}/family_chores/frontend"
exec pnpm dev
