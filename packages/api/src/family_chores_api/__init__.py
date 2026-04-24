"""FastAPI routers, services, schemas, WS, and error envelope for Family Chores.

Exposes `create_app(**deps)` — a deployment-target-agnostic factory that
takes injected collaborators (session factory, HA bridge, WS manager,
options, JWT secret, static dir) and returns a wired FastAPI instance.

The add-on calls this factory from its own lifespan-aware wrapper (the
addon owns DB bootstrap, HA-client construction, APScheduler lifecycle);
the future SaaS backend in `apps/saas-backend/` will call it with a
`PlaceholderAuthStrategy` in Phase 3.

See DECISIONS §11 for refactor context and the Q3/Q4 resolutions that
shape the factory signature (secret injection; BridgeProtocol consumer).
"""

from family_chores_api.app import create_app
from family_chores_api.bridge import BridgeProtocol
from family_chores_api.events import WSManager

__all__ = [
    "BridgeProtocol",
    "WSManager",
    "create_app",
]
