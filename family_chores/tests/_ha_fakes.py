"""In-memory HA test doubles — a FakeHAClient that records calls and a
FakeTodoState that behaves like a single `todo.*` entity.

Not a conftest (it shouldn't auto-register); imported explicitly where used.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

from family_chores_addon.ha.client import HAClientError, HAUnavailableError, TodoItem


@dataclass
class FakeTodoList:
    entity_id: str
    items: list[dict[str, Any]] = field(default_factory=list)


class FakeHAClient:
    """Records every call the bridge/reconciler makes against it.

    Supports get_config, set_state, fire_event, todo_* service calls.
    """

    def __init__(self, *, time_zone: str = "America/Chicago") -> None:
        self._time_zone = time_zone
        self._next_uid = itertools.count(1)
        self.todo_lists: dict[str, FakeTodoList] = {}
        # Call history — each entry is (method, args...)
        self.calls: list[tuple[str, Any]] = []
        # Set `fail_next` to raise on the next call of a given method.
        self.fail_next: dict[str, Exception] = {}

    # ─── test helpers ─────────────────────────────────────────────────────

    def ensure_list(self, entity_id: str) -> FakeTodoList:
        if entity_id not in self.todo_lists:
            self.todo_lists[entity_id] = FakeTodoList(entity_id=entity_id)
        return self.todo_lists[entity_id]

    def _maybe_fail(self, method: str) -> None:
        if method in self.fail_next:
            exc = self.fail_next.pop(method)
            raise exc

    # ─── HAClient interface ───────────────────────────────────────────────

    async def get_config(self) -> dict[str, Any]:
        self._maybe_fail("get_config")
        self.calls.append(("get_config", None))
        return {"version": "2026.4.1", "time_zone": self._time_zone}

    async def set_state(
        self, entity_id: str, state: str, attributes: dict[str, Any] | None = None
    ) -> None:
        self._maybe_fail("set_state")
        self.calls.append(("set_state", (entity_id, state, attributes or {})))

    async def fire_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._maybe_fail("fire_event")
        self.calls.append(("fire_event", (event_type, payload)))

    async def todo_get_items(self, entity_id: str) -> list[TodoItem]:
        self._maybe_fail("todo_get_items")
        self.calls.append(("todo_get_items", entity_id))
        fake_list = self.ensure_list(entity_id)
        return [
            TodoItem(
                uid=str(item["uid"]),
                summary=str(item["summary"]),
                status=str(item.get("status", "needs_action")),
                due=item.get("due"),
                description=item.get("description"),
            )
            for item in fake_list.items
        ]

    async def todo_add_item(
        self,
        entity_id: str,
        summary: str,
        *,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None:
        self._maybe_fail("todo_add_item")
        fake_list = self.ensure_list(entity_id)
        uid = f"uid-{next(self._next_uid)}"
        fake_list.items.append(
            {
                "uid": uid,
                "summary": summary,
                "status": "needs_action",
                "due": due_date.isoformat() if due_date else None,
                "description": description,
            }
        )
        self.calls.append(("todo_add_item", (entity_id, summary, due_date, description)))

    async def todo_update_item(
        self,
        entity_id: str,
        item: str,
        *,
        rename: str | None = None,
        status: str | None = None,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None:
        self._maybe_fail("todo_update_item")
        self.calls.append(
            (
                "todo_update_item",
                (entity_id, item, rename, status, due_date, description),
            )
        )
        fake_list = self.ensure_list(entity_id)
        for it in fake_list.items:
            if it["uid"] == item or it["summary"] == item:
                if rename is not None:
                    it["summary"] = rename
                if status is not None:
                    it["status"] = status
                if due_date is not None:
                    it["due"] = due_date.isoformat()
                if description is not None:
                    it["description"] = description
                return
        raise HAClientError(f"400: item not found: {item}")

    async def todo_remove_item(self, entity_id: str, item: str) -> None:
        self._maybe_fail("todo_remove_item")
        self.calls.append(("todo_remove_item", (entity_id, item)))
        fake_list = self.ensure_list(entity_id)
        before = len(fake_list.items)
        fake_list.items = [
            it for it in fake_list.items if it["uid"] != item and it["summary"] != item
        ]
        if len(fake_list.items) == before:
            raise HAClientError(f"404: item not found: {item}")

    async def aclose(self) -> None:
        self.calls.append(("aclose", None))


__all__ = ["FakeHAClient", "FakeTodoList", "HAClientError", "HAUnavailableError"]
