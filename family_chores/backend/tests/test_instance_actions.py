"""Service-level tests for the instance action functions.

The HTTP layer covers happy paths; this file targets edge cases that need
an injected clock (undo-window expiry) or that are awkward to reach via
the API surface.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from family_chores.api.errors import (
    InvalidStateError,
    NotFoundError,
    UndoWindowExpiredError,
)
from family_chores_core.time import utcnow
from family_chores_db.models import (
    Chore,
    ChoreInstance,
    InstanceState,
    Member,
    RecurrenceType,
)
from family_chores.services.instance_actions import (
    UNDO_WINDOW_SECONDS,
    adjust_member_points,
    approve_instance,
    complete_instance,
    reject_instance,
    skip_instance,
    undo_complete,
)


async def _seed(async_session, *, requires_approval=False):
    member = Member(name="Alice", slug="alice", requires_approval=requires_approval)
    chore = Chore(name="Dishes", points=5, recurrence_type=RecurrenceType.DAILY)
    chore.assigned_members = [member]
    async_session.add_all([member, chore])
    await async_session.flush()
    inst = ChoreInstance(chore_id=chore.id, member_id=member.id, date=date(2026, 4, 21))
    async_session.add(inst)
    await async_session.flush()
    return member, chore, inst


# ─── complete ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_missing_instance_raises(async_session):
    with pytest.raises(NotFoundError):
        await complete_instance(async_session, 999, actor="test")


@pytest.mark.asyncio
async def test_complete_non_pending_raises(async_session):
    _, _, inst = await _seed(async_session)
    await complete_instance(async_session, inst.id, actor="test")
    with pytest.raises(InvalidStateError):
        await complete_instance(async_session, inst.id, actor="test")


# ─── undo ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_undo_within_window(async_session):
    _, _, inst = await _seed(async_session)
    await complete_instance(async_session, inst.id, actor="test")

    reverted = await undo_complete(async_session, inst.id, actor="test")
    assert reverted.state is InstanceState.PENDING
    assert reverted.points_awarded == 0


@pytest.mark.asyncio
async def test_undo_after_window_expired(async_session):
    _, _, inst = await _seed(async_session)
    await complete_instance(async_session, inst.id, actor="test")

    # Fake "now" far past the window.
    future = utcnow() + timedelta(seconds=UNDO_WINDOW_SECONDS + 10)
    with pytest.raises(UndoWindowExpiredError):
        await undo_complete(async_session, inst.id, actor="test", now=future)


@pytest.mark.asyncio
async def test_undo_non_completed_raises(async_session):
    _, _, inst = await _seed(async_session)
    with pytest.raises(InvalidStateError):
        await undo_complete(async_session, inst.id, actor="test")


@pytest.mark.asyncio
async def test_undo_done_unapproved_also_allowed_in_window(async_session):
    _, _, inst = await _seed(async_session, requires_approval=True)
    await complete_instance(async_session, inst.id, actor="kid")
    assert inst.state is InstanceState.DONE_UNAPPROVED

    reverted = await undo_complete(async_session, inst.id, actor="kid")
    assert reverted.state is InstanceState.PENDING


# ─── approve / reject ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_awards_points_and_records_approver(async_session):
    _, _, inst = await _seed(async_session, requires_approval=True)
    await complete_instance(async_session, inst.id, actor="kid")

    approved = await approve_instance(async_session, inst.id, actor="parent-jason")
    assert approved.state is InstanceState.DONE
    assert approved.points_awarded == 5
    assert approved.approved_by == "parent-jason"
    assert approved.approved_at is not None


@pytest.mark.asyncio
async def test_approve_pending_raises(async_session):
    _, _, inst = await _seed(async_session, requires_approval=True)
    with pytest.raises(InvalidStateError):
        await approve_instance(async_session, inst.id, actor="parent")


@pytest.mark.asyncio
async def test_reject_reverts_state(async_session):
    _, _, inst = await _seed(async_session, requires_approval=True)
    await complete_instance(async_session, inst.id, actor="kid")
    reverted = await reject_instance(
        async_session, inst.id, actor="parent", reason="too messy"
    )
    assert reverted.state is InstanceState.PENDING
    assert reverted.completed_at is None


# ─── skip ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_skip_done_raises(async_session):
    _, _, inst = await _seed(async_session)
    await complete_instance(async_session, inst.id, actor="kid")
    with pytest.raises(InvalidStateError):
        await skip_instance(async_session, inst.id, actor="parent")


# ─── points adjust ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_adjust_missing_member_raises(async_session):
    with pytest.raises(NotFoundError):
        await adjust_member_points(async_session, 999, actor="parent", delta=10)


@pytest.mark.asyncio
async def test_adjust_creates_stats_if_absent(async_session):
    m, _, _ = await _seed(async_session)
    stats = await adjust_member_points(async_session, m.id, actor="parent", delta=5)
    assert stats.points_total == 5


@pytest.mark.asyncio
async def test_adjust_clamp_at_zero(async_session):
    m, _, _ = await _seed(async_session)
    await adjust_member_points(async_session, m.id, actor="parent", delta=10)
    stats = await adjust_member_points(async_session, m.id, actor="parent", delta=-100)
    assert stats.points_total == 0
