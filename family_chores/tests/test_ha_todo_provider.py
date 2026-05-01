"""Tests for `HATodoProvider` — the addon's HAClient → TodoProvider
adapter (DECISIONS §14 Tier 1).

The wrapper has two responsibilities:

  1. Method translation — the bridge / reconciler call agnostic
     `add_item` / `get_items` / `update_item` / `remove_item`; the
     wrapper forwards to the HA-specific `todo_*` methods on the client.
  2. Error translation — every `HAClientError` (including subclasses
     for unavailable / unauthorized / 5xx) wraps as `TodoProviderError`
     so the bridge has one exception class to catch.

The `TodoItem` shape is also re-projected from the HA-specific dataclass
into the agnostic one so callers don't depend on the HAClient module.
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest
from family_chores_api.services.todo import (
    TodoItem,
    TodoProviderError,
)

from family_chores_addon.ha.client import (
    HAClient,
    HAClientError,
    HAUnauthorizedError,
    HAUnavailableError,
)
from family_chores_addon.ha.todo import HATodoProvider

from ._ha_fakes import FakeHAClient


def _make_provider() -> tuple[HATodoProvider, FakeHAClient]:
    fake = FakeHAClient()
    provider = HATodoProvider(cast(HAClient, fake))
    return provider, fake


# ─── happy-path delegation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_item_delegates_to_todo_add_item():
    provider, fake = _make_provider()
    await provider.add_item(
        "todo.kid",
        "Dishes",
        due_date=date(2026, 5, 1),
        description="Tonight",
    )
    add_calls = [c for c in fake.calls if c[0] == "todo_add_item"]
    assert len(add_calls) == 1
    _, (entity_id, summary, due, desc) = add_calls[0]
    assert entity_id == "todo.kid"
    assert summary == "Dishes"
    assert due == date(2026, 5, 1)
    assert desc == "Tonight"


@pytest.mark.asyncio
async def test_get_items_returns_agnostic_todo_item():
    """The wrapper reprojects the HA-specific TodoItem into the
    agnostic one. Callers should get instances of the
    `family_chores_api.services.todo.TodoItem` shape, not the HAClient one."""
    provider, fake = _make_provider()
    await provider.add_item("todo.kid", "Dishes", due_date=date(2026, 5, 1))
    items = await provider.get_items("todo.kid")
    assert len(items) == 1
    assert isinstance(items[0], TodoItem)
    assert items[0].summary == "Dishes"
    assert items[0].status == "needs_action"
    assert items[0].due == "2026-05-01"


@pytest.mark.asyncio
async def test_update_item_delegates_with_kwargs():
    provider, fake = _make_provider()
    await provider.add_item("todo.kid", "Dishes")
    items = await provider.get_items("todo.kid")
    uid = items[0].uid

    await provider.update_item(
        "todo.kid",
        uid,
        rename="Wash dishes",
        status="completed",
        due_date=date(2026, 5, 2),
        description="Done!",
    )

    update_calls = [c for c in fake.calls if c[0] == "todo_update_item"]
    assert len(update_calls) == 1
    _, (entity_id, item, rename, status, due_date, description) = update_calls[0]
    assert entity_id == "todo.kid"
    assert item == uid
    assert rename == "Wash dishes"
    assert status == "completed"
    assert due_date == date(2026, 5, 2)
    assert description == "Done!"


@pytest.mark.asyncio
async def test_remove_item_delegates():
    provider, fake = _make_provider()
    await provider.add_item("todo.kid", "Dishes")
    items = await provider.get_items("todo.kid")
    uid = items[0].uid

    await provider.remove_item("todo.kid", uid)

    remove_calls = [c for c in fake.calls if c[0] == "todo_remove_item"]
    assert len(remove_calls) == 1
    _, (entity_id, item) = remove_calls[0]
    assert entity_id == "todo.kid"
    assert item == uid

    # State change reflected.
    leftover = await provider.get_items("todo.kid")
    assert leftover == []


# ─── error translation ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_item_translates_haclient_error():
    provider, fake = _make_provider()
    fake.fail_next["todo_add_item"] = HAClientError("bad request")
    with pytest.raises(TodoProviderError, match="bad request"):
        await provider.add_item("todo.kid", "Dishes")


@pytest.mark.asyncio
async def test_get_items_translates_unavailable_error():
    """Subclasses of HAClientError (unavailable, unauthorized, server)
    all get rolled up to TodoProviderError."""
    provider, fake = _make_provider()
    fake.fail_next["todo_get_items"] = HAUnavailableError("connection refused")
    with pytest.raises(TodoProviderError):
        await provider.get_items("todo.kid")


@pytest.mark.asyncio
async def test_update_item_translates_unauthorized_error():
    provider, fake = _make_provider()
    fake.fail_next["todo_update_item"] = HAUnauthorizedError("401")
    with pytest.raises(TodoProviderError):
        await provider.update_item("todo.kid", "uid-1", status="completed")


@pytest.mark.asyncio
async def test_remove_item_translates_haclient_error():
    provider, fake = _make_provider()
    fake.fail_next["todo_remove_item"] = HAClientError("404")
    with pytest.raises(TodoProviderError):
        await provider.remove_item("todo.kid", "uid-1")


@pytest.mark.asyncio
async def test_translated_error_chain_preserves_cause():
    """The original `HAClientError` is chained via `__cause__` so logs
    still surface the underlying issue."""
    provider, fake = _make_provider()
    original = HAClientError("the real problem")
    fake.fail_next["todo_add_item"] = original
    with pytest.raises(TodoProviderError) as exc_info:
        await provider.add_item("todo.kid", "Dishes")
    assert exc_info.value.__cause__ is original
