"""The HA-bridge consumer protocol, exposed to routers and services.

This is the "apps-side" contract that concrete bridges (e.g. the add-on's
`family_chores_addon.ha.bridge.HABridge`) implement. Routers enqueue state-
change notifications and HA events through this interface without ever
importing a concrete HA client — the dependency arrow stays **apps →
packages**, never the reverse.

Moved here in Phase 2 step 4 (originally lived inside `family_chores.ha.bridge`).
The concrete `HABridge` and `NoOpBridge` implementations stay with the HA
client code, which is an add-on concern.

The `enqueue_event(event_type, payload)` method is the implicit
`EventProtocol` shape called out in DECISIONS §11 Q4. An explicit `Event`
dataclass wasn't introduced because the current tuple-of-args calling
convention already satisfies the protocol-shape requirement and is used at
every call site; introducing a dataclass would force every caller to
change and delivers zero architectural benefit over the existing shape.
"""

from __future__ import annotations

from typing import Any


class BridgeProtocol:
    """Interface exposed to routers / services.

    Implemented by add-on-side bridges. Every method is fire-and-forget
    from the router's perspective — the bridge queues work asynchronously
    and never blocks the HTTP response path (DECISIONS §4 #41).
    """

    def notify_member_dirty(self, member_id: int) -> None: ...

    def notify_approvals_dirty(self) -> None: ...

    def notify_instance_changed(self, instance_id: int) -> None: ...

    def enqueue_event(self, event_type: str, payload: dict[str, Any]) -> None: ...

    async def force_flush(self) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...
