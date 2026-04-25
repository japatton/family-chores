# Family Chores — multi-stage add-on image.
#
# **Build context: repo root** (not `family_chores/`). The addon depends on
# the workspace packages at `packages/{core,db,api}/`, which only exist
# above this Dockerfile in the tree. Build with:
#
#     docker build -f family_chores/Dockerfile -t family-chores .
#
# CI follows the same pattern (see `.github/workflows/ci.yml` and
# `release.yml`). HA Supervisor builds locally use the same context too,
# but Supervisor invokes `docker build` against the addon's directory by
# default — so a production install relies on pulling the multi-arch
# image we push to GHCR via `release.yml`. (Adding an `image:` field to
# `family_chores/config.yaml` makes this explicit; deferred to a
# deployment-config PR.)

ARG BUILD_FROM="ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20"

# ─── Stage 1: frontend build ──────────────────────────────────────────────
# Compiles the React/Vite SPA into family_chores/src/family_chores_addon/static/.
# Runs on Node 22 LTS with pnpm provisioned via corepack; the output is
# pure static HTML/JS/CSS so the final image doesn't need Node at all.
#
# pnpm strict-default install via the workspace root + filter ensures
# reproducible deps from the committed pnpm-lock.yaml (Q6 contract).
FROM node:22-alpine AS frontend-build

WORKDIR /build

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

# Bring just the workspace metadata in first for cache efficiency. Every
# package.json in the workspace must be present so pnpm can resolve
# workspace links, even with --filter narrowing the install scope.
COPY pnpm-workspace.yaml package.json pnpm-lock.yaml ./
COPY family_chores/frontend/package.json ./family_chores/frontend/package.json
COPY apps/web/package.json ./apps/web/package.json
COPY lovelace-card/package.json ./lovelace-card/package.json

# `--filter family-chores-frontend` only fetches deps the SPA needs;
# `--frozen-lockfile` rejects any drift from pnpm-lock.yaml.
RUN pnpm install --frozen-lockfile --filter family-chores-frontend

# Now the rest of the SPA source.
COPY family_chores/frontend ./family_chores/frontend

# Vite's `outDir` resolves to `../src/family_chores_addon/static`
# relative to family_chores/frontend/, i.e. /build/family_chores/src/family_chores_addon/static.
RUN mkdir -p /build/family_chores/src/family_chores_addon/static \
    && pnpm --filter family-chores-frontend build

# ─── Stage 2: backend runtime ─────────────────────────────────────────────
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FAMILY_CHORES_DATA_DIR=/data

# Build tools for argon2-cffi; stripped out after install. Pillow's
# image-codec deps (jpeg-dev, zlib-dev, libjpeg-turbo, zlib) were
# previously here for an avatar-re-encode path that was specced but
# never built — see F-S003 + the pyproject.toml comment. Restore them
# alongside Pillow if avatar uploads land later.
RUN apk add --no-cache --virtual .build-deps \
        build-base \
        libffi-dev \
        openssl-dev \
    && apk add --no-cache \
        tini

WORKDIR /app

# Workspace-package source. `pip install` against each path produces a
# regular (non-editable) install — pip treats local paths the same as
# wheels for resolution purposes, and installing in dependency order
# satisfies family_chores's `family-chores-{core,db,api}` deps without
# pip ever reaching out to PyPI. uv is workspace-aware and would do
# this in a single command, but pip doesn't ship in the HA base image
# any larger than necessary; sticking with the dep-ordered approach
# keeps the runtime image lean.
COPY packages/core /app/packages/core
COPY packages/db /app/packages/db
COPY packages/api /app/packages/api
COPY family_chores/pyproject.toml /app/family_chores/pyproject.toml
COPY family_chores/src /app/family_chores/src

# Overlay the fresh SPA build on top of the (empty) static directory.
COPY --from=frontend-build /build/family_chores/src/family_chores_addon/static \
    /app/family_chores/src/family_chores_addon/static

RUN pip install --no-cache-dir --prefer-binary \
        /app/packages/core \
        /app/packages/db \
        /app/packages/api \
        /app/family_chores \
    && apk del .build-deps

COPY family_chores/run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8099

# Use tini as PID 1 so signals propagate cleanly to uvicorn.
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
