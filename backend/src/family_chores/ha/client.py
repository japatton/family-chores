"""Async HTTP client for Home Assistant's REST API.

Two runtime modes:
  - Inside a Supervisor-managed add-on: `SUPERVISOR_TOKEN` env var is set
    and HA is at `http://supervisor/core/api`. This is the production path.
  - Local dev: user sets `HA_URL` + `HA_TOKEN` directly. Matches the probe
    script pattern.

Everything raises a typed subclass of `HAClientError` so the bridge can
distinguish "HA is down, retry" from "auth failure, stop" from "bad request,
log and drop".
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date as date_type
from typing import Any

import httpx

log = logging.getLogger(__name__)

SUPERVISOR_BASE_URL = "http://supervisor/core/api"
_DEFAULT_TIMEOUT = 10.0
_TODO_STATUS_NEEDS_ACTION = "needs_action"
_TODO_STATUS_COMPLETED = "completed"


class HAClientError(Exception):
    """Base for any failure talking to HA."""


class HAUnavailableError(HAClientError):
    """Network error, timeout, or connection refused."""


class HAUnauthorizedError(HAClientError):
    """401 / 403 from HA — token rejected or role insufficient."""


class HAServerError(HAClientError):
    """HA returned 5xx."""


@dataclass(frozen=True, slots=True)
class TodoItem:
    uid: str
    summary: str
    status: str
    due: str | None
    description: str | None


class HAClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport
        self._http: httpx.AsyncClient | None = None

    def _build_http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base,
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._token}"},
            transport=self._transport,
        )

    async def __aenter__(self) -> HAClient:
        self._http = self._build_http()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def base_url(self) -> str:
        return self._base

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        if self._http is None:
            # Allow single-shot use without the context manager (tests).
            self._http = self._build_http()
        try:
            response = await self._http.request(method, path, json=json, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise HAUnavailableError(str(exc)) from exc

        if response.status_code in (401, 403):
            raise HAUnauthorizedError(f"{response.status_code}: {response.text[:200]}")
        if 500 <= response.status_code < 600:
            raise HAServerError(f"{response.status_code}: {response.text[:200]}")
        if response.status_code >= 400:
            raise HAClientError(f"{response.status_code}: {response.text[:200]}")

        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    # ─── high-level ────────────────────────────────────────────────────────

    async def get_config(self) -> dict[str, Any]:
        result = await self._request("GET", "/config")
        if not isinstance(result, dict):
            raise HAClientError(f"unexpected /config payload: {type(result).__name__}")
        return result

    async def set_state(
        self,
        entity_id: str,
        state: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        body: dict[str, Any] = {"state": state}
        if attributes:
            body["attributes"] = attributes
        await self._request("POST", f"/states/{entity_id}", json=body)

    async def fire_event(self, event_type: str, payload: dict[str, Any]) -> None:
        await self._request("POST", f"/events/{event_type}", json=payload)

    async def call_service(
        self,
        domain: str,
        service: str,
        data: dict[str, Any],
        *,
        return_response: bool = False,
    ) -> Any:
        path = f"/services/{domain}/{service}"
        params = {"return_response": "true"} if return_response else None
        return await self._request("POST", path, json=data, params=params)

    # ─── todo — the 2026.4 way: state attrs don't carry items, must use
    #     `todo.get_items` with return_response=true. ───

    async def todo_get_items(self, entity_id: str) -> list[TodoItem]:
        """Fetch open and completed items for a `todo.*` entity."""
        response = await self.call_service(
            "todo",
            "get_items",
            {"entity_id": entity_id, "status": ["needs_action", "completed"]},
            return_response=True,
        )
        service_response = (response or {}).get("service_response") or {}
        entity_block = service_response.get(entity_id) or {}
        items_raw = entity_block.get("items") or []
        out: list[TodoItem] = []
        for raw in items_raw:
            if not isinstance(raw, dict):
                continue
            out.append(
                TodoItem(
                    uid=str(raw.get("uid") or ""),
                    summary=str(raw.get("summary") or ""),
                    status=str(raw.get("status") or _TODO_STATUS_NEEDS_ACTION),
                    due=raw.get("due"),
                    description=raw.get("description"),
                )
            )
        return out

    async def todo_add_item(
        self,
        entity_id: str,
        summary: str,
        *,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None:
        """Add an item. HA does NOT return a UID — call todo_get_items after."""
        data: dict[str, Any] = {"entity_id": entity_id, "item": summary}
        if due_date is not None:
            data["due_date"] = due_date.isoformat()
        if description is not None:
            data["description"] = description
        await self.call_service("todo", "add_item", data)

    async def todo_update_item(
        self,
        entity_id: str,
        item: str,  # uid or summary
        *,
        rename: str | None = None,
        status: str | None = None,
        due_date: date_type | None = None,
        description: str | None = None,
    ) -> None:
        data: dict[str, Any] = {"entity_id": entity_id, "item": item}
        if rename is not None:
            data["rename"] = rename
        if status is not None:
            if status not in (_TODO_STATUS_NEEDS_ACTION, _TODO_STATUS_COMPLETED):
                raise ValueError(f"invalid todo status: {status!r}")
            data["status"] = status
        if due_date is not None:
            data["due_date"] = due_date.isoformat()
        if description is not None:
            data["description"] = description
        await self.call_service("todo", "update_item", data)

    async def todo_remove_item(self, entity_id: str, item: str) -> None:
        await self.call_service(
            "todo", "remove_item", {"entity_id": entity_id, "item": item}
        )


def make_client_from_env() -> HAClient | None:
    """Construct an HAClient from environment variables.

    Order:
      1. Supervisor — `SUPERVISOR_TOKEN` set by add-on runtime.
      2. Local dev — `HA_URL` + `HA_TOKEN`.
      3. Otherwise None; the bridge falls back to a no-op.
    """
    supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
    if supervisor_token:
        return HAClient(SUPERVISOR_BASE_URL, supervisor_token)
    dev_url = os.environ.get("HA_URL", "").rstrip("/")
    dev_token = os.environ.get("HA_TOKEN")
    if dev_url and dev_token:
        return HAClient(f"{dev_url}/api", dev_token)
    log.info(
        "no HA credentials (SUPERVISOR_TOKEN / HA_URL+HA_TOKEN) — "
        "running with no-op HA bridge"
    )
    return None
