"""HA implementation of `TodoProvider` (DECISIONS §14 Tier 1 sweep).

Thin adapter over `HAClient.todo_*`. The bridge depends on the
agnostic `TodoProvider` Protocol; this class is what gets injected at
addon startup, so the bridge logic stays HA-unaware (matches the
calendar provider pattern).

Errors: HA's typed exception tree (HAUnavailableError, HAUnauthorized,
etc.) is wrapped in `TodoProviderError` so the bridge has a single
catch class. The wrapping preserves the original exception via
`__cause__` so logs still show the underlying cause.
"""

from __future__ import annotations

from datetime import date as date_type

from family_chores_api.services.todo import (
    TodoItem,
    TodoProvider,
    TodoProviderError,
)

from family_chores_addon.ha.client import HAClient, HAClientError


class HATodoProvider(TodoProvider):
    """Wraps `HAClient` so the bridge sees a `TodoProvider` interface."""

    def __init__(self, client: HAClient) -> None:
        self._client = client

    async def add_item(
        self,
        entity_id: str,
        summary: str,
        *,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None:
        try:
            await self._client.todo_add_item(
                entity_id, summary, due_date=due_date, description=description
            )
        except HAClientError as exc:
            raise TodoProviderError(str(exc)) from exc

    async def get_items(self, entity_id: str) -> list[TodoItem]:
        try:
            ha_items = await self._client.todo_get_items(entity_id)
        except HAClientError as exc:
            raise TodoProviderError(str(exc)) from exc
        return [
            TodoItem(
                uid=item.uid,
                summary=item.summary,
                status=item.status,
                due=item.due,
                description=item.description,
            )
            for item in ha_items
        ]

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
        try:
            await self._client.todo_update_item(
                entity_id,
                item,
                rename=rename,
                status=status,
                due_date=due_date,
                description=description,
            )
        except HAClientError as exc:
            raise TodoProviderError(str(exc)) from exc

    async def remove_item(self, entity_id: str, item: str) -> None:
        try:
            await self._client.todo_remove_item(entity_id, item)
        except HAClientError as exc:
            raise TodoProviderError(str(exc)) from exc
