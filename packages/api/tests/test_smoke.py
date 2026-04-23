"""Smoke test — verifies the family-chores-api scaffold is importable.

Real tests (test_api_*, test_instance_service, etc.) arrive in step 4 of
the Phase 2 refactor when routers + services move out of the addon package.
"""

from family_chores_api import __version__


def test_package_importable() -> None:
    assert __version__ == "0.1.0"
