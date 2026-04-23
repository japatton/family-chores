"""Smoke test — verifies the family-chores-db scaffold is importable.

Real tests (test_models, test_startup_recovery, test_migration_0003) arrive
in steps 3 and 8 of the Phase 2 refactor.
"""

from family_chores_db import __version__


def test_package_importable() -> None:
    assert __version__ == "0.1.0"
