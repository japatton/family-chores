ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FAMILY_CHORES_DATA_DIR=/data

# The HA base-python image already ships with Python 3.12 and pip.
# Install build-time headers that some deps (argon2-cffi, pillow) may need,
# then strip the toolchain after install to keep the final image small.
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

# Install the backend package (this also pulls runtime deps from pyproject.toml).
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/src /app/backend/src
RUN pip install --no-cache-dir --prefer-binary /app/backend \
    && apk del .build-deps

COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8099

# Use tini as PID 1 so signals propagate cleanly to uvicorn.
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/run.sh"]
