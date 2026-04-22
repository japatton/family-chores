"""Async bridge that mirrors SQLite state into HA entities.

Design pattern: a single long-lived worker task processes three channels:

  1. **Sensor publishes.** `notify_member_dirty(id)` /
     `notify_approvals_dirty()` accumulate dirty flags. On each flush the
     bridge opens a fresh session, reads current DB state, and POSTs to
     `/api/states/sensor.family_chores_*`.
  2. **Todo sync.** `notify_instance_changed(id)` queues an instance id.
     The bridge looks up the member's `ha_todo_entity_id`; if set, it adds
     / updates / removes a todo item on that list. UIDs are captured by
     calling `todo.get_items` after `todo.add_item` (HA doesn't return the
     UID from the add call).
  3. **Events.** `enqueue_event(type, payload)` buffers events; the bridge
     fires each via `POST /api/events/<type>`.

Debouncing: after wake, the worker sleeps `debounce_seconds` before flushing
so a burst of mutations from one HTTP request collapses into one HA pass.

Error handling: any failure on a single step is caught, logged, and causes
an exponential back-off on the next cycle. We never let one bad call take
down the worker. The scheduler's periodic reconciler converges anything the
bridge dropped.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date as date_type
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from family_chores.db.models import (
    Chore,
    ChoreInstance,
    InstanceState,
    Member,
    MemberStats,
)
from family_chores.ha.client import (
    HAClient,
    HAClientError,
    HAServerError,
    HAUnauthorizedError,
    HAUnavailableError,
)

log = logging.getLogger(__name__)

_DEFAULT_DEBOUNCE = 0.5  # seconds
_BACKOFF_INITIAL = 0.5
_BACKOFF_MAX = 60.0
_EVENT_BACKLOG_LIMIT = 1000

TODO_STATUS_NEEDS_ACTION = "needs_action"
TODO_STATUS_COMPLETED = "completed"

_INSTANCE_STATE_TO_TODO_STATUS = {
    InstanceState.PENDING: TODO_STATUS_NEEDS_ACTION,
    InstanceState.DONE_UNAPPROVED: TODO_STATUS_NEEDS_ACTION,
    InstanceState.DONE: TODO_STATUS_COMPLETED,
    InstanceState.SKIPPED: TODO_STATUS_COMPLETED,
    InstanceState.MISSED: TODO_STATUS_COMPLETED,
}


def fc_tag(instance_id: int) -> str:
    """Prefix that marks a todo item as belonging to a chore instance."""
    return f"[FC#{instance_id}]"


def todo_summary_for(instance_id: int, chore_name: str) -> str:
    return f"{fc_tag(instance_id)} {chore_name}"


def sensor_entity_for_member_points(slug: str) -> str:
    return f"sensor.family_chores_{slug}_points"


def sensor_entity_for_member_streak(slug: str) -> str:
    return f"sensor.family_chores_{slug}_streak"


SENSOR_PENDING_APPROVALS = "sensor.family_chores_pending_approvals"


class BridgeProtocol:
    """Interface exposed to routers / services. Implemented by HABridge and NoOpBridge."""

    def notify_member_dirty(self, member_id: int) -> None: ...

    def notify_approvals_dirty(self) -> None: ...

    def notify_instance_changed(self, instance_id: int) -> None: ...

    def enqueue_event(self, event_type: str, payload: dict[str, Any]) -> None: ...

    async def force_flush(self) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


class NoOpBridge(BridgeProtocol):
    """Stand-in when no HA client is available (dev without HA_URL/TOKEN).

    All notifications are accepted silently; the app runs normally, HA just
    doesn't see mirror state. `DECISIONS §4` guarantees the UI is never
    blocked by HA unavailability.
    """

    def notify_member_dirty(self, member_id: int) -> None:  # pragma: no cover - trivial
        pass

    def notify_approvals_dirty(self) -> None:  # pragma: no cover
        pass

    def notify_instance_changed(self, instance_id: int) -> None:  # pragma: no cover
        pass

    def enqueue_event(self, event_type: str, payload: dict[str, Any]) -> None:  # pragma: no cover
        pass

    async def force_flush(self) -> None:  # pragma: no cover
        pass

    async def start(self) -> None:  # pragma: no cover
        pass

    async def stop(self) -> None:  # pragma: no cover
        pass


class HABridge(BridgeProtocol):
    def __init__(
        self,
        client: HAClient,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        debounce_seconds: float = _DEFAULT_DEBOUNCE,
    ) -> None:
        self._client = client
        self._session_factory = session_factory
        self._debounce = debounce_seconds

        self._dirty_members: set[int] = set()
        self._dirty_approvals = False
        self._dirty_instances: set[int] = set()
        self._event_backlog: list[tuple[str, dict[str, Any]]] = []

        self._wake = asyncio.Event()
        self._stop = False
        self._worker: asyncio.Task[None] | None = None
        self._flush_lock = asyncio.Lock()
        self._backoff = _BACKOFF_INITIAL

    # ─── lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._worker is not None:
            return
        self._stop = False
        self._worker = asyncio.create_task(self._run(), name="ha-bridge-worker")

    async def stop(self) -> None:
        self._stop = True
        self._wake.set()
        if self._worker is not None:
            try:
                await asyncio.wait_for(self._worker, timeout=5.0)
            except asyncio.TimeoutError:
                self._worker.cancel()
            self._worker = None
        await self._client.aclose()

    # ─── notification interface ───────────────────────────────────────────

    def notify_member_dirty(self, member_id: int) -> None:
        self._dirty_members.add(member_id)
        self._wake.set()

    def notify_approvals_dirty(self) -> None:
        self._dirty_approvals = True
        self._wake.set()

    def notify_instance_changed(self, instance_id: int) -> None:
        self._dirty_instances.add(instance_id)
        self._wake.set()

    def enqueue_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if len(self._event_backlog) >= _EVENT_BACKLOG_LIMIT:
            dropped = self._event_backlog.pop(0)
            log.warning("ha event backlog full; dropped oldest: %s", dropped[0])
        self._event_backlog.append((event_type, payload))
        self._wake.set()

    async def force_flush(self) -> None:
        """Run one flush cycle synchronously. Used by tests + the reconciler."""
        async with self._flush_lock:
            await self._flush_once()

    # ─── worker loop ──────────────────────────────────────────────────────

    async def _run(self) -> None:
        while not self._stop:
            try:
                await self._wake.wait()
            except asyncio.CancelledError:
                return
            if self._stop:
                return
            self._wake.clear()
            try:
                await asyncio.sleep(self._debounce)
            except asyncio.CancelledError:
                return
            try:
                async with self._flush_lock:
                    await self._flush_once()
                self._backoff = _BACKOFF_INITIAL
            except HAUnauthorizedError:
                # This won't recover without user action. Log loudly and
                # drop the work so we don't spin forever.
                log.error(
                    "HA rejected our token (401/403). Check add-on "
                    "permissions or HA_TOKEN. Dropping queued work."
                )
                self._drain_all()
            except Exception:  # noqa: BLE001 — last-resort; network / DB / misc
                log.exception("bridge flush failed; will retry")
                await asyncio.sleep(self._backoff)
                self._backoff = min(self._backoff * 2, _BACKOFF_MAX)
                self._wake.set()

    def _drain_all(self) -> None:
        self._dirty_members.clear()
        self._dirty_approvals = False
        self._dirty_instances.clear()
        self._event_backlog.clear()

    # ─── flush logic ──────────────────────────────────────────────────────

    async def _flush_once(self) -> None:
        members_to_publish = set(self._dirty_members)
        self._dirty_members.clear()
        do_approvals = self._dirty_approvals
        self._dirty_approvals = False
        instances_to_sync = set(self._dirty_instances)
        self._dirty_instances.clear()
        events_to_fire = list(self._event_backlog)
        self._event_backlog.clear()

        if not (members_to_publish or do_approvals or instances_to_sync or events_to_fire):
            return

        async with self._session_factory() as session:
            for mid in members_to_publish:
                await self._publish_member_sensors(session, mid)

            if do_approvals:
                await self._publish_pending_approvals(session)

            for iid in instances_to_sync:
                await self._sync_instance_todo(session, iid)

            # Only commit after HA calls succeed — we may have written
            # `ha_todo_uid` back to instances during todo sync.
            await session.commit()

        for event_type, payload in events_to_fire:
            try:
                await self._client.fire_event(event_type, payload)
            except HAUnavailableError:
                # Network blip — requeue for next cycle.
                self._event_backlog.append((event_type, payload))
                raise
            except HAClientError as exc:
                log.warning(
                    "dropping event %s: %s", event_type, exc
                )

    # ─── sensor publishing ───────────────────────────────────────────────

    async def _publish_member_sensors(self, session: AsyncSession, member_id: int) -> None:
        result = await session.execute(
            select(Member)
            .where(Member.id == member_id)
            .options(selectinload(Member.stats))
        )
        member = result.scalar_one_or_none()
        if member is None:
            return
        stats = member.stats
        today_progress = await self._today_progress_pct(session, member_id)

        attrs = {
            "points_this_week": stats.points_this_week if stats else 0,
            "streak": stats.streak if stats else 0,
            "today_progress_pct": today_progress,
            "member_id": member.id,
            "slug": member.slug,
            "name": member.name,
        }
        total = stats.points_total if stats else 0

        points_entity = sensor_entity_for_member_points(member.slug)
        streak_entity = sensor_entity_for_member_streak(member.slug)
        await self._client.set_state(points_entity, str(total), attrs)
        await self._client.set_state(
            streak_entity,
            str(attrs["streak"]),
            {"member_id": member.id, "slug": member.slug, "name": member.name},
        )

    async def _today_progress_pct(self, session: AsyncSession, member_id: int) -> int:
        """Reuse the same query pattern as `/api/today` but for one member."""
        from family_chores.core.time import utcnow

        # We don't want to couple to the FastAPI `Options` tz here — use the
        # stored member_stats.week_anchor? No, that's weekly. Use today in
        # UTC; the scheduler's midnight job will re-publish with the correct
        # local date, and this is a projection anyway.
        today = utcnow().date()
        res = await session.execute(
            select(ChoreInstance.state)
            .where(ChoreInstance.member_id == member_id)
            .where(ChoreInstance.date == today)
        )
        states = list(res.scalars().all())
        if not states:
            return 0
        done = sum(
            1
            for s in states
            if s
            in {
                InstanceState.DONE,
                InstanceState.DONE_UNAPPROVED,
                InstanceState.SKIPPED,
            }
        )
        return int((done / len(states)) * 100)

    async def _publish_pending_approvals(self, session: AsyncSession) -> None:
        count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ChoreInstance)
                    .where(ChoreInstance.state == InstanceState.DONE_UNAPPROVED)
                )
            ).scalar_one()
        )
        await self._client.set_state(
            SENSOR_PENDING_APPROVALS,
            str(count),
            {"friendly_name": "Family Chores — pending approvals"},
        )

    # ─── todo sync ───────────────────────────────────────────────────────

    async def _sync_instance_todo(self, session: AsyncSession, instance_id: int) -> None:
        inst = await session.get(ChoreInstance, instance_id)
        if inst is None:
            return  # instance was deleted; reconciler will clean up orphans
        member = await session.get(Member, inst.member_id)
        if member is None or not member.ha_todo_entity_id:
            return
        entity_id = member.ha_todo_entity_id
        chore = await session.get(Chore, inst.chore_id)
        if chore is None:
            return

        summary = todo_summary_for(inst.id, chore.name)
        status = _INSTANCE_STATE_TO_TODO_STATUS[inst.state]
        due: date_type | None = inst.date

        if inst.ha_todo_uid:
            # Update by UID. If HA lost the item (e.g. user deleted it in
            # the UI), the update will 4xx — we swallow and re-add below.
            try:
                await self._client.todo_update_item(
                    entity_id,
                    inst.ha_todo_uid,
                    rename=summary,
                    status=status,
                    due_date=due,
                )
                return
            except HAClientError as exc:
                log.info(
                    "todo_update_item by uid failed (%s); will re-create", exc
                )
                inst.ha_todo_uid = None

        # No UID known, or update failed — add then capture UID.
        await self._client.todo_add_item(entity_id, summary, due_date=due)
        items = await self._client.todo_get_items(entity_id)
        tag = fc_tag(inst.id)
        for item in items:
            if item.summary.startswith(tag):
                inst.ha_todo_uid = item.uid
                # If the freshly-created item needs status != needs_action,
                # flip it now. (add_item always starts as needs_action.)
                if status != TODO_STATUS_NEEDS_ACTION:
                    try:
                        await self._client.todo_update_item(
                            entity_id, item.uid, status=status
                        )
                    except HAClientError as exc:
                        log.info("follow-up status update failed: %s", exc)
                return
        log.warning(
            "could not locate freshly-added todo item for instance %d in %s",
            inst.id,
            entity_id,
        )


__all__ = [
    "BridgeProtocol",
    "HABridge",
    "NoOpBridge",
    "SENSOR_PENDING_APPROVALS",
    "TODO_STATUS_COMPLETED",
    "TODO_STATUS_NEEDS_ACTION",
    "fc_tag",
    "sensor_entity_for_member_points",
    "sensor_entity_for_member_streak",
    "todo_summary_for",
]
