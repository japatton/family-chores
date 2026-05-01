"""Tests for `NoOpTodoProvider` — every method is a silent no-op.

The no-op provider is the default for the standalone SaaS deployment
and the addon's NoOpBridge path. The bridge / reconciler call methods
on it the same way they would on a real backend; nothing must raise.
"""

from __future__ import annotations

from datetime import date

import pytest

from family_chores_api.services.todo import NoOpTodoProvider, TodoProvider


@pytest.mark.asyncio
async def test_noop_satisfies_todo_provider_protocol():
    """Sanity check: the no-op should satisfy the Protocol shape so
    callers that type-hint `TodoProvider` accept it without a cast."""
    provider: TodoProvider = NoOpTodoProvider()
    assert provider is not None


@pytest.mark.asyncio
async def test_add_item_returns_none_silently():
    provider = NoOpTodoProvider()
    result = await provider.add_item(
        "todo.kid", "Dishes", due_date=date(2026, 5, 1), description="Tonight"
    )
    assert result is None


@pytest.mark.asyncio
async def test_get_items_returns_empty_list():
    provider = NoOpTodoProvider()
    items = await provider.get_items("todo.kid")
    assert items == []


@pytest.mark.asyncio
async def test_update_item_returns_none_silently():
    provider = NoOpTodoProvider()
    result = await provider.update_item(
        "todo.kid",
        "uid-1",
        rename="Renamed",
        status="completed",
        due_date=date(2026, 5, 1),
    )
    assert result is None


@pytest.mark.asyncio
async def test_remove_item_returns_none_silently():
    provider = NoOpTodoProvider()
    result = await provider.remove_item("todo.kid", "uid-1")
    assert result is None


@pytest.mark.asyncio
async def test_full_lifecycle_no_state_persists():
    """Add then get returns empty — the no-op doesn't actually store
    anything (which is exactly what 'no-op' means)."""
    provider = NoOpTodoProvider()
    await provider.add_item("todo.kid", "Dishes")
    items = await provider.get_items("todo.kid")
    assert items == []
