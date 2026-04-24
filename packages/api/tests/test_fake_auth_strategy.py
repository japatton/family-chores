"""Smoke test for the `FakeAuthStrategy` fixture (defined in conftest.py).

The fixture is the headline test artefact added in step 5 for use by the
step-9 scoping integration tests in `family_chores/tests/`. This file
exists so `pytest packages/api/tests/` collects at least one test (an
empty test dir exits 5, which trips `scripts/lint.sh`'s `set -e`) and
so the fixture has at least one consumer right next to its definition.

The "real" multi-tenant integration consumers live in
`family_chores/tests/test_household_scoping.py`, which inlines its own
copy of `FakeAuthStrategy` because pytest's `--import-mode=importlib`
doesn't share fixtures across test packages.
"""

from __future__ import annotations

import pytest

from family_chores_api.deps.auth import Identity, ParentIdentity


@pytest.mark.asyncio
async def test_fake_auth_strategy_default_identity(fake_auth_strategy):
    """Default fixture instance returns a parent identity, no household."""
    identity = await fake_auth_strategy.identify(request=None)  # type: ignore[arg-type]
    assert isinstance(identity, Identity)
    assert identity.user_key == "tester"
    assert identity.household_id is None
    assert identity.is_parent is True


@pytest.mark.asyncio
async def test_fake_auth_strategy_default_require_parent(fake_auth_strategy):
    parent = await fake_auth_strategy.require_parent(request=None)  # type: ignore[arg-type]
    assert isinstance(parent, ParentIdentity)
    assert parent.user_key == "tester"
    assert parent.household_id is None
    assert parent.expires_at > 0
