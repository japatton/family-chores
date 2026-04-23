"""Database layer for Family Chores.

Owns SQLAlchemy models, Alembic migrations, the engine/session factory, the
SQLite PRAGMA connect hooks, the `scoped()` tenant-filter helper, and the
WAL-aware recovery/backup utilities.

Apps call `recovery.ensure_db_ready(...)` from their own lifespan. This
package MUST stay free of HA-specific dependencies.

See `DECISIONS.md` §11. Code migrates in here during step 3 of the Phase 2
monorepo refactor; step 1 is scaffold-only.
"""

__version__ = "0.1.0"
