"""HAClient HTTP-level tests via httpx.MockTransport."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from family_chores_addon.ha.client import (
    HAClient,
    HAClientError,
    HAServerError,
    HAUnauthorizedError,
    HAUnavailableError,
    TodoItem,
)


def _make_client(handler) -> HAClient:
    transport = httpx.MockTransport(handler)
    return HAClient("http://supervisor/core/api", "tok", transport=transport)


@pytest.mark.asyncio
async def test_get_config_returns_parsed_json():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Bearer tok"
        assert req.url.path == "/core/api/config"
        return httpx.Response(200, json={"version": "2026.4.1", "time_zone": "America/Chicago"})

    client = _make_client(handler)
    try:
        cfg = await client.get_config()
        assert cfg["version"] == "2026.4.1"
        assert cfg["time_zone"] == "America/Chicago"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_set_state_posts_expected_body():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    client = _make_client(handler)
    try:
        await client.set_state(
            "sensor.family_chores_alice_points", "42", {"streak": 7, "points_this_week": 10}
        )
    finally:
        await client.aclose()
    assert captured["path"] == "/core/api/states/sensor.family_chores_alice_points"
    assert captured["body"] == {"state": "42", "attributes": {"streak": 7, "points_this_week": 10}}


@pytest.mark.asyncio
async def test_fire_event_posts_payload():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"message": "Event fired."})

    client = _make_client(handler)
    try:
        await client.fire_event("family_chores_completed", {"member_id": 1, "points": 5})
    finally:
        await client.aclose()
    assert captured["path"] == "/core/api/events/family_chores_completed"
    assert captured["body"] == {"member_id": 1, "points": 5}


@pytest.mark.asyncio
async def test_todo_get_items_parses_service_response():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/core/api/services/todo/get_items"
        assert req.url.params["return_response"] == "true"
        body = json.loads(req.content)
        assert body["entity_id"] == "todo.alice"
        assert body["status"] == ["needs_action", "completed"]
        return httpx.Response(
            200,
            json={
                "service_response": {
                    "todo.alice": {
                        "items": [
                            {"uid": "abc", "summary": "A", "status": "needs_action"},
                            {
                                "uid": "xyz",
                                "summary": "B",
                                "status": "completed",
                                "due": "2026-05-01",
                            },
                        ]
                    }
                }
            },
        )

    client = _make_client(handler)
    try:
        items = await client.todo_get_items("todo.alice")
    finally:
        await client.aclose()
    assert items == [
        TodoItem(uid="abc", summary="A", status="needs_action", due=None, description=None),
        TodoItem(uid="xyz", summary="B", status="completed", due="2026-05-01", description=None),
    ]


@pytest.mark.asyncio
async def test_todo_add_item_sends_iso_due_date():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    client = _make_client(handler)
    try:
        await client.todo_add_item(
            "todo.alice", "Dishes", due_date=date(2026, 5, 1), description="do the dishes"
        )
    finally:
        await client.aclose()
    assert captured["body"] == {
        "entity_id": "todo.alice",
        "item": "Dishes",
        "due_date": "2026-05-01",
        "description": "do the dishes",
    }


@pytest.mark.asyncio
async def test_todo_update_item_rejects_bad_status():
    client = _make_client(lambda req: httpx.Response(200, json={}))
    try:
        with pytest.raises(ValueError):
            await client.todo_update_item("todo.alice", "uid", status="wat")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_unauthorized_raises_unauthorized_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    client = _make_client(handler)
    try:
        with pytest.raises(HAUnauthorizedError):
            await client.get_config()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_5xx_raises_server_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="down")

    client = _make_client(handler)
    try:
        with pytest.raises(HAServerError):
            await client.get_config()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_network_error_raises_unavailable():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("cannot connect")

    client = _make_client(handler)
    try:
        with pytest.raises(HAUnavailableError):
            await client.get_config()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_4xx_raises_generic_client_error():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad"})

    client = _make_client(handler)
    try:
        with pytest.raises(HAClientError):
            await client.fire_event("e", {})
    finally:
        await client.aclose()
