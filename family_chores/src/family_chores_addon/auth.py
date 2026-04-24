"""HA Ingress concrete `AuthStrategy` implementation.

Reads identity from the `X-Remote-User` header that HA Supervisor
injects on every Ingress-proxied request, and verifies parent elevation
against the in-memory parent JWT (decisions §4 #34, §11 Q3).

Constructed by the addon's lifespan with a `secret_provider` callable so
the JWT secret is fetched fresh from `app.state.jwt_secret` at every
request — there's no module-level secret constant (Q3 contract).

In single-tenant add-on mode `household_id` is always `None`. The
service-layer `scoped()` helper (step 9) treats `None` as "no filter",
preserving the pre-refactor query semantics.

Step 6 will move this file along with the rest of the addon into
`family_chores/src/family_chores_addon/auth.py` when the `backend/`
wrapper is flattened (Q8).
"""

from __future__ import annotations

from collections.abc import Callable

import jwt
from family_chores_api.deps.auth import Identity, ParentIdentity
from family_chores_api.errors import AuthRequiredError
from family_chores_api.security import decode_parent_token, extract_bearer
from fastapi import Request


class IngressAuthStrategy:
    """`AuthStrategy` for the HA Ingress single-tenant add-on."""

    def __init__(self, secret_provider: Callable[[], str]) -> None:
        self._secret_provider = secret_provider

    @staticmethod
    def _user_from(request: Request) -> str:
        """Pull `X-Remote-User`; fall back to `"anonymous"` for local dev."""
        return request.headers.get("X-Remote-User", "").strip() or "anonymous"

    async def identify(self, request: Request) -> Identity:
        user = self._user_from(request)
        is_parent = False
        token = extract_bearer(request.headers.get("Authorization"))
        if token:
            try:
                decode_parent_token(self._secret_provider(), token)
                is_parent = True
            except jwt.InvalidTokenError:
                pass
        return Identity(user_key=user, household_id=None, is_parent=is_parent)

    async def require_parent(self, request: Request) -> ParentIdentity:
        token = extract_bearer(request.headers.get("Authorization"))
        if not token:
            raise AuthRequiredError("parent mode required")
        try:
            claim = decode_parent_token(self._secret_provider(), token)
        except jwt.InvalidTokenError as exc:
            raise AuthRequiredError("parent mode required") from exc
        return ParentIdentity(
            user_key=self._user_from(request),
            household_id=None,
            expires_at=claim.exp,
        )
