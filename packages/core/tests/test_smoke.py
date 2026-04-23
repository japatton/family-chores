"""Smoke test — verifies the family-chores-core scaffold is importable.

Real tests (test_recurrence, test_streaks, test_points) arrive in step 2 of
the Phase 2 refactor when `core/` is moved out of the addon package.
"""

from family_chores_core import __version__


def test_package_importable() -> None:
    assert __version__ == "0.1.0"
