"""FastAPI dependencies: session, user identity, parent-role gate."""

from __future__ import annotations

from collections.abc import AsyncIterator

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from family_chores.api.errors import AuthRequiredError, ForbiddenError
from family_chores.api.events import WSManager
from family_chores.config import Options
from family_chores.security import ParentClaim, decode_parent_token


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_ws_manager(request: Request) -> WSManager:
    return request.app.state.ws_manager


def get_options(request: Request) -> Options:
    return request.app.state.options


def get_jwt_secret(request: Request) -> str:
    return request.app.state.jwt_secret


def get_bridge(request: Request):
    """Return the HA bridge (either HABridge or NoOpBridge)."""
    return request.app.state.bridge


def get_effective_timezone(request: Request) -> str:
    """Cached HA tz (if fetched at startup), override, or UTC."""
    cached = getattr(request.app.state, "effective_timezone", None)
    if isinstance(cached, str) and cached:
        return cached
    opts: Options = request.app.state.options
    return opts.effective_timezone


def get_remote_user(request: Request) -> str:
    """Identity from the Ingress `X-Remote-User` header.

    Supervisor sets this on every request it proxies. For local dev without
    Ingress we fall back to "anonymous" so the app still works.
    """
    user = request.headers.get("X-Remote-User", "").strip()
    return user or "anonymous"


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def maybe_parent(
    authorization: str | None = Header(None),
    secret: str = Depends(get_jwt_secret),
) -> ParentClaim | None:
    """Return a ParentClaim if a valid token is present, else None.

    Does NOT raise on missing/invalid tokens — use `require_parent` for that.
    Useful for endpoints that reveal extra data when parent mode is active.
    """
    token = _extract_bearer(authorization)
    if not token:
        return None
    try:
        return decode_parent_token(secret, token)
    except jwt.InvalidTokenError:
        return None


def require_parent(claim: ParentClaim | None = Depends(maybe_parent)) -> ParentClaim:
    if claim is None:
        raise AuthRequiredError("parent mode required")
    return claim


def require_role(role: str):
    """Factory that returns a dependency enforcing a specific role."""

    def _dep(claim: ParentClaim = Depends(require_parent)) -> ParentClaim:
        # parent is our only role for now; keep the factory so the HA bridge
        # (milestone 5) can later introduce distinct service-token roles.
        if role == "parent":
            return claim
        raise ForbiddenError(f"unknown role {role}")

    return _dep
