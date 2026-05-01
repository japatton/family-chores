"""Reconciler — makes the todo backend's state match ours.

Runs on a schedule (every 15 min) and at startup. Safety net against events
the bridge dropped (backend down for a while, upgrade window, etc.).

Algorithm, per member with `ha_todo_entity_id` set:

  1. Fetch the backend's current items for that entity via
     `TodoProvider.get_items` (Tier 1 sweep — DECISIONS §14).
  2. Load our open-range instances (date >= today) and recent completed ones
     (date >= today - backfill days) so we don't delete a recently-completed
     item the user still wants to see on the list.
  3. Match by our `[FC#<id>]` prefix.
     - In backend but not ours → delete (orphan).
     - In ours but not backend → create; capture UID.
     - Both → if summary/status/due drift, update; always record UID.

Missing chores / deleted instances are caught by step (a): the DB won't have
the FC id anymore, so the backend item looks like an orphan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import timedelta

from family_chores_api.services.todo import (
    TodoItem,
    TodoProvider,
    TodoProviderError,
)
from family_chores_db.models import ChoreInstance, Member
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from family_chores_addon.ha.bridge import (
    _INSTANCE_STATE_TO_TODO_STATUS,
    TODO_STATUS_NEEDS_ACTION,
    fc_tag,
    todo_summary_for,
)

log = logging.getLogger(__name__)

RECONCILE_BACKFILL_DAYS = 7


@dataclass(slots=True)
class ReconcileResult:
    members_processed: int = 0
    items_created: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_fc_id(summary: str) -> int | None:
    """Extract the instance id from a `[FC#<n>] ...` summary, if any."""
    if not summary.startswith("[FC#"):
        return None
    end = summary.find("]")
    if end < 0:
        return None
    try:
        return int(summary[4:end])
    except ValueError:
        return None


def _needs_update(
    item: TodoItem,
    expected_summary: str,
    expected_status: str,
    expected_due: str | None,
) -> bool:
    if item.summary != expected_summary:
        return True
    if item.status != expected_status:
        return True
    # Normalise both to ISO date-only strings for comparison.
    item_due_normalised = item.due.split("T", 1)[0] if isinstance(item.due, str) else None
    return item_due_normalised != expected_due


async def reconcile_once(
    todos: TodoProvider,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    today: date_type,
    backfill_days: int = RECONCILE_BACKFILL_DAYS,
) -> ReconcileResult:
    """Tier 1 sweep (DECISIONS §14): now takes a `TodoProvider` rather
    than the HA client directly, so the same reconciler logic runs
    against any backend conforming to the Protocol (HA, Google Tasks,
    a future SaaS in-app store, etc.). Existing callers wrap the
    `HAClient` in `HATodoProvider`.
    """
    result = ReconcileResult()
    async with session_factory() as session:
        members_res = await session.execute(
            select(Member).where(Member.ha_todo_entity_id.is_not(None))
        )
        members = list(members_res.scalars().all())

        for member in members:
            try:
                await _reconcile_one_member(
                    session, todos, member, today=today, backfill_days=backfill_days, result=result
                )
            except TodoProviderError as exc:
                msg = f"member={member.slug} entity={member.ha_todo_entity_id}: {exc}"
                log.warning("reconcile error: %s", msg)
                result.errors.append(msg)
            result.members_processed += 1
        await session.commit()
    return result


async def _reconcile_one_member(
    session: AsyncSession,
    todos: TodoProvider,
    member: Member,
    *,
    today: date_type,
    backfill_days: int,
    result: ReconcileResult,
) -> None:
    entity_id = member.ha_todo_entity_id
    assert entity_id is not None  # caller filters

    backend_items = await todos.get_items(entity_id)

    start = today - timedelta(days=backfill_days)
    inst_res = await session.execute(
        select(ChoreInstance)
        .where(ChoreInstance.member_id == member.id)
        .where(ChoreInstance.date >= start)
        .options(selectinload(ChoreInstance.chore))
    )
    our_instances = list(inst_res.scalars().all())
    our_by_id: dict[int, ChoreInstance] = {i.id: i for i in our_instances}

    # First pass: walk backend items.
    for item in backend_items:
        fc_id = _parse_fc_id(item.summary)
        if fc_id is None:
            # Not one of ours — leave it alone.
            continue
        our_inst = our_by_id.pop(fc_id, None)
        if our_inst is None:
            # Orphan — our side has no such instance any more.
            try:
                await todos.remove_item(entity_id, item.uid)
                result.items_deleted += 1
            except TodoProviderError as exc:
                log.warning("failed to delete orphan %s: %s", item.uid, exc)
                result.errors.append(f"delete {item.uid}: {exc}")
            continue

        # Record UID if we didn't have one.
        if not our_inst.ha_todo_uid:
            our_inst.ha_todo_uid = item.uid

        expected_summary = todo_summary_for(our_inst.id, our_inst.chore.name)
        expected_status = _INSTANCE_STATE_TO_TODO_STATUS[our_inst.state]
        expected_due = our_inst.date.isoformat()
        if _needs_update(item, expected_summary, expected_status, expected_due):
            try:
                await todos.update_item(
                    entity_id,
                    item.uid,
                    rename=expected_summary,
                    status=expected_status,
                    due_date=our_inst.date,
                )
                result.items_updated += 1
            except TodoProviderError as exc:
                log.warning("failed to update %s: %s", item.uid, exc)
                result.errors.append(f"update {item.uid}: {exc}")

    # Second pass: anything still in our_by_id is missing from the
    # backend — create it.
    for inst in our_by_id.values():
        summary = todo_summary_for(inst.id, inst.chore.name)
        try:
            await todos.add_item(entity_id, summary, due_date=inst.date)
            result.items_created += 1
        except TodoProviderError as exc:
            log.warning("failed to add item for instance %s: %s", inst.id, exc)
            result.errors.append(f"add #{inst.id}: {exc}")
            continue

    # Third pass: sweep UIDs for any we just added.
    if our_by_id:
        try:
            fresh = await todos.get_items(entity_id)
        except TodoProviderError as exc:
            log.warning("uid-sweep get_items failed: %s", exc)
            return
        by_tag: dict[str, TodoItem] = {
            _parse_tag_str(it.summary): it for it in fresh if _parse_fc_id(it.summary) is not None
        }
        for inst in our_by_id.values():
            tag = fc_tag(inst.id)
            fresh_item = by_tag.get(tag)
            if fresh_item is not None:
                inst.ha_todo_uid = fresh_item.uid
                # Fix status if needed: add_item always creates needs_action,
                # so a completed instance needs a status flip.
                expected_status = _INSTANCE_STATE_TO_TODO_STATUS[inst.state]
                if expected_status != TODO_STATUS_NEEDS_ACTION:
                    try:
                        await todos.update_item(
                            entity_id, fresh_item.uid, status=expected_status
                        )
                    except TodoProviderError as exc:
                        log.info("post-create status flip failed: %s", exc)


def _parse_tag_str(summary: str) -> str:
    """Return just the `[FC#N]` portion of a summary, or empty string."""
    if not summary.startswith("[FC#"):
        return ""
    end = summary.find("]")
    if end < 0:
        return ""
    return summary[: end + 1]


__all__ = ["ReconcileResult", "reconcile_once"]
