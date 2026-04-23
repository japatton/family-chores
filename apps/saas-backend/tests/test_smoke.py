"""Smoke test — verifies the family-chores-saas scaffold is importable.

Real tests (app starts, /health returns 200, every other endpoint returns
501) arrive in step 10 of the Phase 2 refactor.
"""

from family_chores_saas import __version__


def test_package_importable() -> None:
    assert __version__ == "0.1.0"
