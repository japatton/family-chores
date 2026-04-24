"""Auth-strategy abstraction + the existing legacy auth deps.

The **`AuthStrategy` Protocol** is the seam that lets the same routers run
under any deployment target's identity model:

  - The add-on installs `IngressAuthStrategy` (reads the Ingress
    remote-user header + verifies the in-memory parent JWT).
  - The future SaaS backend (Phase 3) will install a JWT-based strategy
    that verifies a bearer token from Supabase / Clerk / whatever.
  - Tests install `FakeAuthStrategy` (in `packages/api/tests/_fakes.py`)
    that returns a fixed identity + household_id.

The deployment target's lifespan attaches a concrete strategy to
`app.state.auth_strategy`. `get_auth_strategy(request)` reads it back.

**Backward-compat shims** (`get_remote_user`, `maybe_parent`,
`require_parent`, `require_role`) preserve the historical dep names that
every router uses today, but are now thin wrappers that delegate through
the strategy. This keeps the routers untouched while ensuring every
deployment target's auth contract actually flows through `AuthStrategy`
(otherwise a `PlaceholderAuthStrategy` could be installed and the routers
would still happily read the remote-user header directly — defeating the point).

Tenant scope (`household_id`) is carried on `Identity` but isn't yet
filtered against by the service layer — that's step 9. The plumbing is in
place from step 5.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, cast

from fastapi import Depends, Request

from family_chores_api.errors import AuthRequiredError, ForbiddenError
from family_chores_api.security import ParentClaim


@dataclass(frozen=True, slots=True)
class Identity:
    """Who's making this request, plus a parent-elevation flag.

    `household_id` is `None` in single-tenant add-on mode and a UUID-string
    in (future) multi-tenant SaaS mode. Carried on every request so the
    service layer can scope queries (step 9 plumbing).
    """

    user_key: str
    household_id: str | None
    is_parent: bool


@dataclass(frozen=True, slots=True)
class ParentIdentity:
    """A successfully parent-elevated request.

    Returned by `AuthStrategy.require_parent`. The `expires_at` is the
    unix timestamp at which the underlying token expires (5-minute TTL
    for the addon — DECISIONS §4 #34); the SPA refreshes via
    `/api/auth/refresh` before that lapses (decision §4 #53).
    """

    user_key: str
    household_id: str | None
    expires_at: int


class AuthStrategy(Protocol):
    """The auth contract every deployment target implements.

    Both methods take the raw `Request` so a strategy can read whatever
    headers / cookies / query params it cares about. Implementations must
    raise `AuthRequiredError` from `require_parent` when parent elevation
    isn't satisfied (the `maybe_parent` shim catches that to return None).
    """

    async def identify(self, request: Request) -> Identity: ...

    async def require_parent(self, request: Request) -> ParentIdentity: ...


# ─── Strategy-fetching deps ───────────────────────────────────────────────


def get_auth_strategy(request: Request) -> AuthStrategy:
    """Return the strategy installed on `app.state` by the lifespan."""
    return cast(AuthStrategy, request.app.state.auth_strategy)


async def get_identity(
    request: Request,
    strategy: AuthStrategy = Depends(get_auth_strategy),
) -> Identity:
    return await strategy.identify(request)


async def get_parent_identity(
    request: Request,
    strategy: AuthStrategy = Depends(get_auth_strategy),
) -> ParentIdentity:
    return await strategy.require_parent(request)


# ─── Backward-compat shims (see module docstring) ─────────────────────────


async def get_remote_user(identity: Identity = Depends(get_identity)) -> str:
    """Stable user identifier — historical name for `Identity.user_key`."""
    return identity.user_key


async def maybe_parent(
    request: Request,
    strategy: AuthStrategy = Depends(get_auth_strategy),
) -> ParentClaim | None:
    """Return a ParentClaim if the request has valid parent auth, else None.

    Distinct from `get_parent_identity` — does NOT raise. Used by routes
    that reveal extra data when parent mode is active but stay accessible
    otherwise.
    """
    try:
        parent = await strategy.require_parent(request)
    except AuthRequiredError:
        return None
    return ParentClaim(user=parent.user_key, exp=parent.expires_at)


async def require_parent(
    parent: ParentIdentity = Depends(get_parent_identity),
) -> ParentClaim:
    """Backward-compat: return ParentClaim (older routers expect this type)."""
    return ParentClaim(user=parent.user_key, exp=parent.expires_at)


def require_role(role: str) -> Callable[..., Awaitable[ParentClaim]]:
    """Factory that returns a dep enforcing a specific role.

    Parent is the only role today; the factory exists so future service-
    token / household-admin roles can be added without rewriting every
    router that currently does `Depends(require_parent)`.
    """

    async def _dep(claim: ParentClaim = Depends(require_parent)) -> ParentClaim:
        if role == "parent":
            return claim
        raise ForbiddenError(f"unknown role {role}")

    return _dep
