"""FastAPI dependencies for Family Chores routers.

The single-file `deps.py` was split into this subpackage in Phase 2 step 5
when `AuthStrategy` was introduced. Submodule layout:

  - `auth.py`     — `AuthStrategy` Protocol, `Identity`, `ParentIdentity`,
                    plus historic shims (`get_remote_user`, `maybe_parent`,
                    `require_parent`, `require_role`) that delegate to the
                    strategy.
  - `bridge.py`   — `get_bridge`.
  - `db.py`       — `get_session`.
  - `runtime.py`  — `get_jwt_secret`, `get_effective_timezone`,
                    `get_week_starts_on`, `get_ws_manager`.
  - `tenant.py`   — `get_current_household_id` (Phase 2 step 9 plumbing).

This `__init__.py` re-exports every public name so existing routers'
`from family_chores_api.deps import (...)` lines keep working unchanged.
"""

from family_chores_api.deps.auth import (
    AuthStrategy,
    Identity,
    ParentIdentity,
    get_auth_strategy,
    get_identity,
    get_parent_identity,
    get_remote_user,
    maybe_parent,
    require_parent,
    require_role,
)
from family_chores_api.deps.bridge import get_bridge
from family_chores_api.deps.db import get_session
from family_chores_api.deps.runtime import (
    get_effective_timezone,
    get_jwt_secret,
    get_week_starts_on,
    get_ws_manager,
)
from family_chores_api.deps.tenant import get_current_household_id
from family_chores_api.security import ParentClaim

__all__ = [
    # Auth-strategy abstraction (new in step 5)
    "AuthStrategy",
    "Identity",
    "ParentIdentity",
    "get_auth_strategy",
    "get_identity",
    "get_parent_identity",
    # Backward-compat auth shims
    "ParentClaim",
    "get_remote_user",
    "maybe_parent",
    "require_parent",
    "require_role",
    # State / runtime deps
    "get_bridge",
    "get_current_household_id",
    "get_effective_timezone",
    "get_jwt_secret",
    "get_session",
    "get_week_starts_on",
    "get_ws_manager",
]
