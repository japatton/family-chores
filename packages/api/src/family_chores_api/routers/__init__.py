"""Router modules — collected here for `app.py` to include in one block.

Each submodule defines a `router: APIRouter`. `create_app` mounts them all.

(WS endpoint also lives in this package as `routers/ws.py` — it's just
another APIRouter; the WSManager singleton lives in `family_chores_api.events`.)
"""

from family_chores_api.routers import (
    admin,
    auth,
    chores,
    instances,
    members,
    suggestions,
    ws,
)

__all__ = ["admin", "auth", "chores", "instances", "members", "suggestions", "ws"]
