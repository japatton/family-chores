"""Argon2 PIN hashing + HS256 parent-JWT helpers.

Threat model (see README): the parent PIN is a soft lock keeping kids out of
admin, not a security boundary. Use argon2 anyway — it's cheap, available,
and means a leaked DB doesn't immediately expose a 4-digit PIN.

**Secret-injection contract (DECISIONS §11 Q3).**
This module never reads or stashes the JWT signing secret in a
module-level constant. `mint_parent_token(secret, ...)` and
`decode_parent_token(secret, ...)` always take the secret as an explicit
parameter. Each deployment target is responsible for sourcing its own
secret and passing it in:

  - **Add-on** (`family_chores`): minted on first boot via
    `ensure_jwt_secret(session)` (below), stashed in the `app_config`
    SQLite row, cached on `app.state.jwt_secret` by the addon's lifespan.
  - **Future SaaS** (`apps/saas-backend/`): will read from an env var or
    secret manager and pass the same string in.

`ensure_jwt_secret` itself wraps the SQLite-backed `app_config` row and is
therefore DB-aware (which is OK here — `family_chores_db` is a workspace
dep). The future SaaS won't call `ensure_jwt_secret`; it will populate
`app.state.jwt_secret` from its own secret source.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, cast

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_db.models import AppConfig

_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"
PARENT_JWT_TTL_SECONDS = 5 * 60
JWT_SECRET_KEY = "jwt_secret"
PARENT_PIN_HASH_KEY = "parent_pin_hash"


def extract_bearer(authorization: str | None) -> str | None:
    """Pull a bearer token out of an `Authorization` header value, or return None.

    Public helper because both `deps/auth.py` (the in-package shims) and
    every concrete `AuthStrategy` (the addon's `IngressAuthStrategy`, the
    saas scaffold's `PlaceholderAuthStrategy`) need to parse the header.
    """
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


@dataclass(frozen=True, slots=True)
class ParentClaim:
    user: str
    exp: int


def hash_pin(pin: str) -> str:
    return _hasher.hash(pin)


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        _hasher.verify(hashed, pin)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


async def ensure_jwt_secret(session: AsyncSession) -> str:
    """Mint a JWT secret on first ever boot, otherwise return the stored one.

    Idempotent: always commits if a secret was just minted, otherwise reads.
    """
    row = await session.get(AppConfig, JWT_SECRET_KEY)
    if row is None:
        secret = secrets.token_urlsafe(32)
        session.add(AppConfig(key=JWT_SECRET_KEY, value=secret))
        await session.commit()
        return secret
    return cast(str, row.value)


async def get_pin_hash(session: AsyncSession) -> str | None:
    row = await session.get(AppConfig, PARENT_PIN_HASH_KEY)
    if row is None:
        return None
    return cast(str, row.value)


async def set_pin_hash(session: AsyncSession, pin_hash: str) -> None:
    row = await session.get(AppConfig, PARENT_PIN_HASH_KEY)
    if row is None:
        session.add(AppConfig(key=PARENT_PIN_HASH_KEY, value=pin_hash))
    else:
        row.value = pin_hash
    await session.flush()


async def clear_pin_hash(session: AsyncSession) -> None:
    row = await session.get(AppConfig, PARENT_PIN_HASH_KEY)
    if row is not None:
        await session.delete(row)
        await session.flush()


def mint_parent_token(
    secret: str, user: str, *, ttl_seconds: int = PARENT_JWT_TTL_SECONDS
) -> tuple[str, int]:
    """Issue a short-lived parent-scoped JWT. Returns (token, exp_unix)."""
    now = int(time.time())
    exp = now + ttl_seconds
    payload: dict[str, Any] = {
        "sub": user,
        "role": "parent",
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)
    return token, exp


def decode_parent_token(secret: str, token: str) -> ParentClaim:
    """Decode and validate a parent token. Raises `jwt.InvalidTokenError` on failure."""
    payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    if payload.get("role") != "parent":
        raise jwt.InvalidTokenError("token is not scoped for parent role")
    return ParentClaim(user=str(payload.get("sub", "")), exp=int(payload["exp"]))
