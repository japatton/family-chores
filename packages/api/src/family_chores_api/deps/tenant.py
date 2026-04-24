"""Tenant-scope (`household_id`) dep.

Reads the household_id off the current `Identity`. In single-tenant
add-on mode this is always `None`, which the service-layer `scoped()`
helper interprets as "no household filter" — matching pre-refactor
behavior. In future multi-tenant SaaS mode this will be the
authenticated household's UUID.

The actual query scoping (every service threading this through to the
ORM) lands in step 9.
"""

from __future__ import annotations

from fastapi import Depends

from family_chores_api.deps.auth import Identity, get_identity


async def get_current_household_id(
    identity: Identity = Depends(get_identity),
) -> str | None:
    return identity.household_id
