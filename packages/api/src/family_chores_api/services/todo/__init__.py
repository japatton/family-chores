"""Todo provider abstraction (Tier 1 sweep — DECISIONS §14 Tier 1).

Symmetric to `services/calendar/`. The HA add-on's bridge currently
calls `HAClient.todo_*` directly; introducing this Protocol decouples
the bridge from a specific backend so a future SaaS deployment can
plug in a no-op or a different external service (Google Tasks,
CalDAV, etc.) without changing the bridge logic itself.

Public surface:
  - `TodoItem` — agnostic shape for one item.
  - `TodoProvider` Protocol — `add_item`, `get_items`, `update_item`,
    `remove_item`. Matches the HA service surface; concrete
    implementations live next to their backend.
  - `TodoProviderError` — base for backend failures the bridge can
    catch in one place.
"""

from family_chores_api.services.todo.provider import (
    NoOpTodoProvider,
    TodoItem,
    TodoProvider,
    TodoProviderError,
)

__all__ = ["NoOpTodoProvider", "TodoItem", "TodoProvider", "TodoProviderError"]
