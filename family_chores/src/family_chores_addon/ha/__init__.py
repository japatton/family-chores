"""Home Assistant bridge — one-way mirror of SQLite state into HA entities.

The bridge is intentionally write-only. Business logic NEVER reads entity
state back from HA; everything the app decides is decided from SQLite. HA
is a projection surface for automations and dashboards.

See DECISIONS §4 data-flow rules for why, and §8 for the live-probe findings
that shaped this module (especially the need for `todo.get_items` calls to
learn UIDs — HA 2026.4 doesn't surface items in entity state attributes).
"""

from family_chores_addon.ha.bridge import HABridge, NoOpBridge
from family_chores_addon.ha.calendar import HACalendarProvider
from family_chores_addon.ha.client import (
    HAClient,
    HAClientError,
    HAServerError,
    HAUnauthorizedError,
    HAUnavailableError,
    make_client_from_env,
)

__all__ = [
    "HABridge",
    "HACalendarProvider",
    "HAClient",
    "HAClientError",
    "HAServerError",
    "HAUnauthorizedError",
    "HAUnavailableError",
    "NoOpBridge",
    "make_client_from_env",
]
