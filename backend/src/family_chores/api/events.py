"""WebSocket broadcast manager + event-type constants.

The protocol is intentionally dumb: any state change is broadcast as a
small JSON payload with a `type` and an ID. The client is responsible for
refetching any resource it cares about. We don't push full snapshots —
that would double the data model and couple the UI to message shape.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

log = logging.getLogger(__name__)

EVT_MEMBER_CREATED = "member_created"
EVT_MEMBER_UPDATED = "member_updated"
EVT_MEMBER_DELETED = "member_deleted"

EVT_CHORE_CREATED = "chore_created"
EVT_CHORE_UPDATED = "chore_updated"
EVT_CHORE_DELETED = "chore_deleted"

EVT_INSTANCE_UPDATED = "instance_updated"

EVT_PIN_SET = "pin_set"
EVT_PIN_CLEARED = "pin_cleared"

EVT_STATS_REBUILT = "stats_rebuilt"


class WSManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> int:
        """Send `event` to every connected client. Returns the delivery count."""
        async with self._lock:
            clients = list(self._clients)
        delivered = 0
        dead: list[WebSocket] = []
        for ws in clients:
            if ws.client_state is not WebSocketState.CONNECTED:
                dead.append(ws)
                continue
            try:
                await ws.send_json(event)
                delivered += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        if dead:
            log.debug("pruned %d dead ws clients", len(dead))
        return delivered
