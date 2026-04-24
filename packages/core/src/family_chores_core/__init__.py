"""Pure domain logic for Family Chores.

Shared by every deployment target (HA add-on, future SaaS backend, future
mobile backend). This package MUST stay free of HA-specific dependencies
and data-layer dependencies (no SQLAlchemy, no httpx, no FastAPI).

See `DECISIONS.md` §11 for refactor context. Code migrates in here during
step 2 of the Phase 2 monorepo refactor; step 1 is scaffold-only.
"""

__version__ = "0.1.0"
