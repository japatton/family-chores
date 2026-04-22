"""WebSocket endpoint at `/api/ws`.

The server sends a `{"type":"hello"}` frame on connect and then broadcasts
any mutation event. Clients can send `ping` text frames and will receive
`pong` back — mostly so the frontend can detect dropped connections.

`get_ws_manager` depends on `Request`, which is HTTP-only; `WebSocket` is a
different Starlette connection type. We pull the manager straight off
`ws.app.state` instead of going through a dep.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from family_chores.api.events import WSManager

router = APIRouter()


@router.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    mgr: WSManager = ws.app.state.ws_manager
    await mgr.connect(ws)
    try:
        await ws.send_json({"type": "hello"})
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await mgr.disconnect(ws)
