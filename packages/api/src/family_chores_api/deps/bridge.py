"""HA-bridge dep.

Reads the bridge off `app.state.bridge`. The deployment target's lifespan
installs either a real bridge implementation (with a live HA connection)
or a no-op stand-in when no HA endpoint is configured. See DECISIONS
§4 #40 for the addon's selection logic.
"""

from __future__ import annotations

from typing import cast

from fastapi import Request

from family_chores_api.bridge import BridgeProtocol


def get_bridge(request: Request) -> BridgeProtocol:
    return cast(BridgeProtocol, request.app.state.bridge)
