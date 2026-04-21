"""Alembic environment — sync engine against the same SQLite file.

The app runs on an async SQLAlchemy engine (aiosqlite). Alembic itself runs
sync — both point to the same file on disk. Pragmas are applied on connect
so migrations honour `foreign_keys=ON`.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

from family_chores.db.base import Base, _install_sqlite_pragmas, make_sync_db_url
from family_chores.db import models  # noqa: F401 — registers tables on Base.metadata


config = context.config

# Resolve DB URL: honour a URL that was set programmatically (via
# `cfg.set_main_option("sqlalchemy.url", ...)` from the app's bootstrap code),
# otherwise derive from FAMILY_CHORES_DB or fall back to ./local-data.
_configured_url = config.get_main_option("sqlalchemy.url")
if not _configured_url:
    env_db = os.environ.get("FAMILY_CHORES_DB")
    if env_db:
        db_path = Path(env_db)
    else:
        db_path = Path(os.environ.get("FAMILY_CHORES_DATA_DIR", "local-data")) / "family_chores.db"
    config.set_main_option("sqlalchemy.url", make_sync_db_url(db_path))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite column ops
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(config.get_main_option("sqlalchemy.url"), future=True)
    _install_sqlite_pragmas(engine)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
