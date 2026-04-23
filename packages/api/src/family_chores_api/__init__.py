"""FastAPI application factory, routers, services, schemas, and WS for Family Chores.

Exposes `create_app(*, auth_strategy, bridge, secret_provider, ...)` — a
deployment-target-agnostic factory. The add-on and (future) SaaS backend
each construct their own app by injecting the right `AuthStrategy` and
`BridgeProtocol`.

See `DECISIONS.md` §11 for the refactor context and the injection contract
(Q3 secret-injection, Q4 EventProtocol). Code migrates in here during step
4 of the Phase 2 refactor; step 1 is scaffold-only.
"""

__version__ = "0.1.0"
