#!/bin/sh
# Family Chores add-on entrypoint.
# We intentionally do not use bashio — options are read directly from
# /data/options.json by the Python config loader.
set -eu

mkdir -p /data /data/avatars

exec python -m family_chores_addon
