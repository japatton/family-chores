"""DB session dep.

Reads the async session factory off `app.state` (set by the deployment
target's lifespan from `family_chores_db.make_session_factory(...)`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session
