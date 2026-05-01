"""`TodoProvider` Protocol + agnostic `TodoItem` (DECISIONS §14 Tier 1).

The bridge in the HA add-on (`family_chores_addon.ha.bridge.HABridge`)
mirrors chore instances onto a kid's `todo.*` list — add when a chore
is assigned, update on completion, remove on delete. Until this
Protocol existed the bridge was hard-coded to call `HAClient.todo_*`;
the seam lets us swap in:

  - `NoOpTodoProvider` for the standalone-without-todos case (PR-A
    ships this for the addon test suite; the SaaS deployment will
    use it as the default).
  - A future Google Tasks / CalDAV / Microsoft Todo provider for
    standalone deployments that want a real external surface.
  - The existing HA-backed implementation (`HATodoProvider` in the
    addon, a thin wrapper around `HAClient`).

Status semantics — the bridge maps `InstanceState` to one of two
status strings: `"needs_action"` and `"completed"`. Providers MUST
accept both verbatim (subclassing in some other vocabulary is the
provider's responsibility, not the bridge's).

Errors: providers raise `TodoProviderError` (or a subclass) for any
backend failure the bridge should treat as "transient, will retry".
The bridge has its own back-off logic; providers don't need to retry
internally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TodoItem:
    """Agnostic shape returned by `TodoProvider.get_items`.

    `uid` is the provider-assigned stable id used for subsequent
    updates / removes. `due` is left as a string because providers
    return wildly different formats (HA: ISO date or datetime; CalDAV:
    iCal DATE-TIME; Google: RFC 3339) — the bridge currently only uses
    it for diagnostic logging, so keeping it opaque avoids a
    parsing-error class for no benefit.
    """

    uid: str
    summary: str
    status: str
    due: str | None
    description: str | None


class TodoProviderError(Exception):
    """Base for any failure inside a `TodoProvider` implementation.

    Concrete providers wrap their native exceptions (HAClientError,
    google.auth.exceptions.AuthError, etc.) into this so the bridge
    only has to know about one error class.
    """


class TodoProvider(Protocol):
    """The contract every backend's todo surface implements.

    All four methods are async and idempotent on the data they own
    (a re-add of the same `(entity_id, summary)` pair MAY produce a
    duplicate — backend-dependent — but a re-update or re-remove on
    a non-existent uid raises `TodoProviderError`).
    """

    async def add_item(
        self,
        entity_id: str,
        summary: str,
        *,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None: ...

    async def get_items(self, entity_id: str) -> list[TodoItem]: ...

    async def update_item(
        self,
        entity_id: str,
        item: str,  # uid or summary, provider-dependent
        *,
        rename: str | None = None,
        status: str | None = None,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None: ...

    async def remove_item(self, entity_id: str, item: str) -> None: ...


class NoOpTodoProvider(TodoProvider):
    """Stand-in for deployments without a todo backend.

    All four methods are silent no-ops; `get_items` returns an empty
    list. Used by:
      - The standalone SaaS target (default — no HA / Google Tasks
        wiring out of the box).
      - Addon tests that don't care about todo sync.
      - The addon's `NoOpBridge` path (no HA credentials at all).

    The bridge's `force_flush` and reconciler still run when this is
    the active provider; the calls just don't fan out.
    """

    async def add_item(
        self,
        entity_id: str,
        summary: str,
        *,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None:
        return

    async def get_items(self, entity_id: str) -> list[TodoItem]:
        return []

    async def update_item(
        self,
        entity_id: str,
        item: str,
        *,
        rename: str | None = None,
        status: str | None = None,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None:
        return

    async def remove_item(self, entity_id: str, item: str) -> None:
        return
