"""SaaS placeholder `AuthStrategy` — Phase 3 stub.

Raises `HTTPException(501)` on every method so the saas scaffold's
existing routers (the unmodified `family_chores_api` ones) report
"not implemented" cleanly without the wiring being half-done.

Wired into a proper SaaS app factory in step 10 of the Phase 2 refactor;
real JWT-based identity verification (Supabase / Clerk / etc.) lands in
Phase 3.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from family_chores_api.deps.auth import Identity, ParentIdentity


class PlaceholderAuthStrategy:
    """Always 501. The SaaS auth model isn't built yet."""

    _MSG = "SaaS auth not yet implemented (see DECISIONS §11 — Phase 3)."

    async def identify(self, request: Request) -> Identity:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=self._MSG)

    async def require_parent(self, request: Request) -> ParentIdentity:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=self._MSG)
