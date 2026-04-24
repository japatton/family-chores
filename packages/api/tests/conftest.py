"""Shared fixtures for the `family_chores_api` test suite.

`FakeAuthStrategy` lives here (rather than in a sibling `_fakes.py`) so
other tests in this package can access it via the fixture only — pytest's
`--import-mode=importlib` doesn't put the tests directory on sys.path,
so a sibling-module import wouldn't resolve.

Step 9's scoping tests (planned to live alongside the household_id
service-layer threading) consume this fixture to verify queries are
scoped correctly under both `household_id=None` (single-tenant) and
`household_id="abc"` (multi-tenant) modes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest
from fastapi import Request

from family_chores_api.deps.auth import Identity, ParentIdentity
from family_chores_api.errors import AuthRequiredError


@dataclass
class FakeAuthStrategy:
    """Configurable in-memory `AuthStrategy` for tests.

    - `user_key` / `household_id` / `is_parent` set the values returned
      from `identify`.
    - `parent_ttl_seconds` controls the `expires_at` returned from
      `require_parent`.
    - When `is_parent=False`, `require_parent` raises `AuthRequiredError`
      to mirror the real Ingress / JWT strategies' contract.
    """

    user_key: str = "tester"
    household_id: str | None = None
    is_parent: bool = True
    parent_ttl_seconds: int = 300

    async def identify(self, request: Request) -> Identity:
        return Identity(
            user_key=self.user_key,
            household_id=self.household_id,
            is_parent=self.is_parent,
        )

    async def require_parent(self, request: Request) -> ParentIdentity:
        if not self.is_parent:
            raise AuthRequiredError("parent mode required")
        return ParentIdentity(
            user_key=self.user_key,
            household_id=self.household_id,
            expires_at=int(time.time()) + self.parent_ttl_seconds,
        )


@pytest.fixture
def fake_auth_strategy() -> FakeAuthStrategy:
    """Default fake — anonymous parent, no household.

    Tests that need a different shape construct their own:
        strategy = FakeAuthStrategy(household_id="abc", is_parent=False)
    """
    return FakeAuthStrategy()
