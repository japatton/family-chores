#!/bin/sh
# Vite dev server with /api proxied to the local backend on :8099.
set -eu

cd "$(dirname "$0")/../frontend"

if [ ! -d node_modules ]; then
    npm install
fi

exec npm run dev
