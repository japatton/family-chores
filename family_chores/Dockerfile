# Global ARG — must precede the first FROM to be visible to every stage's
# FROM line. Default points at the amd64 base-python image so a plain
# `docker build .` still works; HA Supervisor overrides this per arch via
# --build-arg from build.yaml.
ARG BUILD_FROM="ghcr.io/home-assistant/amd64-base-python:3.12-alpine3.20"

# ─── Stage 1: frontend build ──────────────────────────────────────────────
# Compiles the React/Vite SPA into src/family_chores_addon/static/. Runs
# on Node 22 LTS; the output is pure static HTML/JS/CSS so the final
# image doesn't need Node at all.
#
# Layout note: the addon flattened in Phase 2 step 6 (DECISIONS §11) —
# the previous `backend/` wrapper was removed so the Python source now
# sits at `src/family_chores_addon/` rather than `backend/src/family_chores/`.
#
# Tooling note (step 7): the frontend now lives in a pnpm workspace at
# the repo root, but HA Supervisor builds the addon with `family_chores/`
# as the Docker build context — so the workspace lockfile at
# `/Users/.../pnpm-lock.yaml` is not reachable from inside the build.
# Step 12 will revisit the addon image to make the Docker build fully
# reproducible across the workspace; for now we use
# `--ignore-workspace --no-frozen-lockfile` so the stage parses and
# (locally) builds, even though resolution isn't pinned.
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

# Activate pnpm via corepack — Node 22 ships it bundled, no extra image.
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

# Install deps. See "Tooling note" above for the workspace caveats.
COPY frontend/package.json ./
RUN pnpm install --ignore-workspace --no-frozen-lockfile

# Copy the rest of the frontend source.
COPY frontend/ ./

# Vite's `outDir` is `../src/family_chores_addon/static` — create the
# target path up front so the relative resolve works.
RUN mkdir -p /app/src/family_chores_addon \
    && pnpm run build

# ─── Stage 2: backend runtime ─────────────────────────────────────────────
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FAMILY_CHORES_DATA_DIR=/data

# Build tools for Pillow/argon2; stripped out after install.
RUN apk add --no-cache --virtual .build-deps \
        build-base \
        libffi-dev \
        openssl-dev \
        jpeg-dev \
        zlib-dev \
    && apk add --no-cache \
        libjpeg-turbo \
        zlib \
        tini

WORKDIR /app

# Backend source first.
COPY pyproject.toml /app/pyproject.toml
COPY src /app/src

# Overlay the fresh SPA build on top of the (empty) static directory.
COPY --from=frontend-build /app/src/family_chores_addon/static \
    /app/src/family_chores_addon/static

RUN pip install --no-cache-dir --prefer-binary /app \
    && apk del .build-deps

COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8099

# Use tini as PID 1 so signals propagate cleanly to uvicorn.
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
