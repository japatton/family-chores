"""Per-instance state transitions: complete / undo / approve / reject / skip
and the sibling `adjust_member_points` for manual parent corrections.

Each function mutates the DB, writes an activity-log row, and returns the
resulting `ChoreInstance` (or MemberStats for the points helper). Commit is
the caller's responsibility — routers own the transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from family_chores_api.errors import (
    InvalidStateError,
    NotFoundError,
    UndoWindowExpiredError,
)
from family_chores_core.time import utcnow
from family_chores_db.models import (
    ActivityLog,
    Chore,
    ChoreInstance,
    InstanceState,
    Member,
    MemberStats,
)

UNDO_WINDOW_SECONDS = 4


async def _load_instance(session: AsyncSession, instance_id: int) -> ChoreInstance:
    inst = await session.get(ChoreInstance, instance_id)
    if inst is None:
        raise NotFoundError(f"instance {instance_id} not found")
    return inst


async def _load_chore(session: AsyncSession, chore_id: int) -> Chore:
    chore = await session.get(Chore, chore_id)
    if chore is None:  # shouldn't happen given FK CASCADE, but defensive
        raise NotFoundError(f"chore {chore_id} not found")
    return chore


async def _load_member(session: AsyncSession, member_id: int) -> Member:
    m = await session.get(Member, member_id)
    if m is None:
        raise NotFoundError(f"member {member_id} not found")
    return m


def _log(session: AsyncSession, actor: str, action: str, payload: dict[str, Any]) -> None:
    session.add(ActivityLog(actor=actor, action=action, payload=payload))


async def complete_instance(
    session: AsyncSession,
    instance_id: int,
    *,
    actor: str,
    now: datetime | None = None,
) -> ChoreInstance:
    """Mark PENDING → DONE (or DONE_UNAPPROVED if member requires approval)."""
    now = now if now is not None else utcnow()
    inst = await _load_instance(session, instance_id)

    if inst.state is not InstanceState.PENDING:
        raise InvalidStateError(
            f"can only complete PENDING instances; current state is {inst.state.value}"
        )

    chore = await _load_chore(session, inst.chore_id)
    member = await _load_member(session, inst.member_id)

    inst.completed_at = now
    if member.requires_approval:
        inst.state = InstanceState.DONE_UNAPPROVED
        inst.points_awarded = 0
        _log(
            session,
            actor,
            "instance_completed",
            {
                "instance_id": inst.id,
                "chore_id": chore.id,
                "member_id": member.id,
                "requires_approval": True,
                "points": 0,
            },
        )
    else:
        inst.state = InstanceState.DONE
        inst.points_awarded = chore.points
        _log(
            session,
            actor,
            "instance_completed",
            {
                "instance_id": inst.id,
                "chore_id": chore.id,
                "member_id": member.id,
                "requires_approval": False,
                "points": chore.points,
            },
        )
    await session.flush()
    return inst


async def undo_complete(
    session: AsyncSession,
    instance_id: int,
    *,
    actor: str,
    now: datetime | None = None,
    window_seconds: int = UNDO_WINDOW_SECONDS,
) -> ChoreInstance:
    now = now if now is not None else utcnow()
    inst = await _load_instance(session, instance_id)

    if inst.state not in {InstanceState.DONE, InstanceState.DONE_UNAPPROVED}:
        raise InvalidStateError(
            f"can only undo completed instances; current state is {inst.state.value}"
        )
    if inst.completed_at is None:
        raise InvalidStateError("instance missing completed_at — cannot compute undo window")

    # `completed_at` is naive UTC (DB convention).
    elapsed = (now - inst.completed_at).total_seconds()
    if elapsed > window_seconds:
        raise UndoWindowExpiredError(
            f"undo window of {window_seconds}s has elapsed ({elapsed:.1f}s since completion)"
        )

    inst.state = InstanceState.PENDING
    inst.completed_at = None
    inst.approved_at = None
    inst.approved_by = None
    inst.points_awarded = 0
    _log(
        session,
        actor,
        "instance_undone",
        {"instance_id": inst.id, "chore_id": inst.chore_id, "member_id": inst.member_id},
    )
    await session.flush()
    return inst


async def approve_instance(
    session: AsyncSession,
    instance_id: int,
    *,
    actor: str,
    now: datetime | None = None,
) -> ChoreInstance:
    now = now if now is not None else utcnow()
    inst = await _load_instance(session, instance_id)

    if inst.state is not InstanceState.DONE_UNAPPROVED:
        raise InvalidStateError(
            f"can only approve DONE_UNAPPROVED instances; current state is {inst.state.value}"
        )

    chore = await _load_chore(session, inst.chore_id)
    inst.state = InstanceState.DONE
    inst.approved_at = now
    inst.approved_by = actor
    inst.points_awarded = chore.points
    _log(
        session,
        actor,
        "instance_approved",
        {
            "instance_id": inst.id,
            "chore_id": chore.id,
            "member_id": inst.member_id,
            "points": chore.points,
        },
    )
    await session.flush()
    return inst


async def reject_instance(
    session: AsyncSession,
    instance_id: int,
    *,
    actor: str,
    reason: str | None = None,
) -> ChoreInstance:
    inst = await _load_instance(session, instance_id)

    if inst.state is not InstanceState.DONE_UNAPPROVED:
        raise InvalidStateError(
            f"can only reject DONE_UNAPPROVED instances; current state is {inst.state.value}"
        )

    inst.state = InstanceState.PENDING
    inst.completed_at = None
    inst.approved_at = None
    inst.approved_by = None
    inst.points_awarded = 0
    _log(
        session,
        actor,
        "instance_rejected",
        {
            "instance_id": inst.id,
            "chore_id": inst.chore_id,
            "member_id": inst.member_id,
            "reason": reason,
        },
    )
    await session.flush()
    return inst


async def skip_instance(
    session: AsyncSession,
    instance_id: int,
    *,
    actor: str,
    reason: str | None = None,
) -> ChoreInstance:
    inst = await _load_instance(session, instance_id)

    if inst.state in {InstanceState.DONE, InstanceState.SKIPPED}:
        raise InvalidStateError(
            f"cannot skip an instance in state {inst.state.value}"
        )

    inst.state = InstanceState.SKIPPED
    inst.points_awarded = 0
    _log(
        session,
        actor,
        "instance_skipped",
        {
            "instance_id": inst.id,
            "chore_id": inst.chore_id,
            "member_id": inst.member_id,
            "reason": reason,
        },
    )
    await session.flush()
    return inst


async def adjust_member_points(
    session: AsyncSession,
    member_id: int,
    *,
    actor: str,
    delta: int,
    reason: str | None = None,
) -> MemberStats:
    """Manually add (or subtract via negative delta) to a member's lifetime total.

    Clamps total at 0 — negative deltas past the current total leave the
    balance at 0 rather than going negative.
    """
    member = await _load_member(session, member_id)
    stats = await session.get(MemberStats, member_id)
    if stats is None:
        # Initialise explicitly — `mapped_column(default=0)` only fires at
        # INSERT, and we need the Python-side attribute populated *before*
        # we do arithmetic on it.
        stats = MemberStats(
            member_id=member.id,
            points_total=0,
            points_this_week=0,
            streak=0,
        )
        session.add(stats)

    stats.points_total = max(0, (stats.points_total or 0) + delta)

    _log(
        session,
        actor,
        "points_adjusted",
        {"member_id": member.id, "delta": delta, "reason": reason},
    )
    await session.flush()
    return stats
