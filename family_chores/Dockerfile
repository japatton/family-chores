# ─── Stage 1: frontend build ──────────────────────────────────────────────
# Compiles the React/Vite SPA into backend/src/family_chores/static/.
# Runs on Node 22 LTS; the output is pure static HTML/JS/CSS so the final
# image doesn't need Node at all.
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

# Install deps from lockfile first for cache efficiency.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Copy the rest of the frontend source.
COPY frontend/ ./

# Vite's `outDir` is `../backend/src/family_chores/static` — create the
# target path up front so the relative resolve works.
RUN mkdir -p /app/backend/src/family_chores \
    && npm run build

# ─── Stage 2: backend runtime ─────────────────────────────────────────────
ARG BUILD_FROM
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

# Backend source first (including an empty `static/` + `.gitkeep`).
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src /app/backend/src

# Overlay the fresh SPA build on top of the (empty) static directory.
COPY --from=frontend-build /app/backend/src/family_chores/static \
    /app/backend/src/family_chores/static

RUN pip install --no-cache-dir --prefer-binary /app/backend \
    && apk del .build-deps

COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8099

# Use tini as PID 1 so signals propagate cleanly to uvicorn.
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
