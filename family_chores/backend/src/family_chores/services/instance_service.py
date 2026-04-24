"""Instance generation + overdue marking.

Both operations are **idempotent**: running them twice on the same day is
a no-op the second time, and running them on startup (as the lifespan
catch-up) produces the same state as running them at midnight.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from family_chores_core.recurrence import dates_due
from family_chores.db.models import Chore, ChoreInstance, InstanceState

INSTANCE_HORIZON_DAYS = 14


async def generate_instances(
    session: AsyncSession,
    *,
    today: date,
    horizon_days: int = INSTANCE_HORIZON_DAYS,
) -> int:
    """Ensure a `ChoreInstance` row exists for every `(chore, member, date)`
    tuple that the recurrence rules require in `[today, today+horizon_days]`.

    Existing rows are never touched — state progress is preserved. Returns
    the number of *new* rows inserted.
    """
    end = today + timedelta(days=horizon_days)

    chore_result = await session.execute(
        select(Chore)
        .where(Chore.active.is_(True))
        .options(selectinload(Chore.assigned_members))
    )
    chores: Sequence[Chore] = chore_result.scalars().all()

    existing_result = await session.execute(
        select(ChoreInstance.chore_id, ChoreInstance.member_id, ChoreInstance.date)
        .where(ChoreInstance.date >= today)
        .where(ChoreInstance.date <= end)
    )
    existing: set[tuple[int, int, date]] = {tuple(row) for row in existing_result.all()}

    new_rows: list[ChoreInstance] = []
    for chore in chores:
        due = dates_due(chore.recurrence_type, chore.recurrence_config, today, end)
        if not due:
            continue
        for member in chore.assigned_members:
            for d in due:
                key = (chore.id, member.id, d)
                if key in existing:
                    continue
                new_rows.append(
                    ChoreInstance(chore_id=chore.id, member_id=member.id, date=d)
                )
                existing.add(key)

    if new_rows:
        session.add_all(new_rows)
        await session.flush()
    return len(new_rows)


async def mark_overdue(session: AsyncSession, *, today: date) -> int:
    """Mark every `pending` or `done_unapproved` instance with `date < today`
    as `missed`. Returns the number of rows updated.

    We iterate ORM objects rather than issuing a bulk UPDATE so the
    `updated_at` column's `onupdate=utcnow` fires correctly.
    """
    result = await session.execute(
        select(ChoreInstance)
        .where(ChoreInstance.date < today)
        .where(
            ChoreInstance.state.in_(
                [InstanceState.PENDING, InstanceState.DONE_UNAPPROVED]
            )
        )
    )
    instances = list(result.scalars().all())
    for inst in instances:
        inst.state = InstanceState.MISSED
    if instances:
        await session.flush()
    return len(instances)
