#!/usr/bin/env python3
"""Home Assistant API probe for the Family Chores bridge design.

Runs a small, fully-reversible set of probes against a live HA instance:
  1. GET  /api/config                           — version, tz, location
  2. GET  /api/services                         — todo.* domain services + schemas
  3. GET  /api/states                           — existing todo.* entities
  4. POST /api/services/todo/add_item           — add one probe item
     GET  /api/states/<target>                  — read it back, find the UID
     POST /api/services/todo/update_item        — update by UID
     POST /api/services/todo/remove_item        — clean up (by UID and by summary)
  5. POST /api/events/family_chores_probe       — test event firing

Every step prints its status and response so the output is copy-pasteable.

    HA_URL=http://homeassistant.local:8123 \
    HA_TOKEN=eyJ... \
    python3 scripts/probe_ha.py > probe_output.txt

The token is read from env only — never logged or written to disk by this
script. Delete it once you're done.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

HA_URL = os.environ.get("HA_URL", "http://homeassistant.local:8123").rstrip("/")
TOKEN = os.environ.get("HA_TOKEN", "")
PROBE_MARKER = "family-chores-probe"

if not TOKEN:
    sys.stderr.write("HA_TOKEN env var is required.\n")
    sys.exit(1)


def request(
    method: str, path: str, body: object | None = None, timeout: float = 15.0
) -> tuple[int, object]:
    url = HA_URL + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return resp.status, None
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001
        return 0, repr(exc)


def hr(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"== {title}")
    print("=" * 72)


def dump(obj: object) -> None:
    if isinstance(obj, (dict, list)):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(repr(obj))


# ─── 1. /api/config ────────────────────────────────────────────────────────

hr("1. GET /api/config")
status, cfg = request("GET", "/api/config")
print(f"status: {status}")
if isinstance(cfg, dict):
    interesting = {
        k: cfg.get(k)
        for k in (
            "version",
            "time_zone",
            "location_name",
            "country",
            "language",
            "latitude",
            "longitude",
            "unit_system",
        )
    }
    dump(interesting)
    components = cfg.get("components")
    if isinstance(components, list):
        has_todo = any(c == "todo" or c.startswith("todo.") for c in components)
        print(f"\ntodo integration loaded: {has_todo}")
else:
    dump(cfg)

# ─── 2. /api/services for todo ─────────────────────────────────────────────

hr("2. /api/services — todo domain only")
status, services = request("GET", "/api/services")
print(f"status: {status}")
todo_domain = None
if isinstance(services, list):
    for domain in services:
        if isinstance(domain, dict) and domain.get("domain") == "todo":
            todo_domain = domain
            break
if todo_domain is None:
    print("No `todo` domain in /api/services — ensure the todo integration is enabled.")
else:
    for svc_name, svc_def in todo_domain.get("services", {}).items():
        print(f"\n--- todo.{svc_name} ---")
        dump(svc_def)

# ─── 3. existing todo.* entities ───────────────────────────────────────────

hr("3. /api/states — todo.* entities")
status, states = request("GET", "/api/states")
print(f"status: {status}")
todo_states: list[dict] = []
if isinstance(states, list):
    todo_states = [
        s
        for s in states
        if isinstance(s, dict) and s.get("entity_id", "").startswith("todo.")
    ]

for s in todo_states:
    attrs = s.get("attributes", {}) or {}
    print(
        f"\n - {s['entity_id']}  state={s.get('state')!r}  attr_keys={sorted(attrs.keys())}"
    )
    items = attrs.get("items")
    if isinstance(items, list) and items:
        print("   sample item:")
        dump(items[0])

if not todo_states:
    print("\nNo todo.* entities found. Create one (Settings → Devices → Add → Local To-do) and rerun.")
    sys.exit(2)

target_entity = next(
    (s["entity_id"] for s in todo_states if s["entity_id"] == "todo.shopping_list"),
    todo_states[0]["entity_id"],
)
print(f"\nprobe target: {target_entity}")

# ─── 4a. add_item with return_response ─────────────────────────────────────

hr("4a. POST /api/services/todo/add_item?return_response=true")
status, resp = request(
    "POST",
    "/api/services/todo/add_item?return_response=true",
    {
        "entity_id": target_entity,
        "item": PROBE_MARKER,
        "due_date": "2026-05-01",
    },
)
print(f"status: {status}")
dump(resp)

if status == 400:
    # Some HA versions / platforms don't support return_response — fall back.
    hr("4a'. retry without return_response")
    status, resp = request(
        "POST",
        "/api/services/todo/add_item",
        {"entity_id": target_entity, "item": PROBE_MARKER, "due_date": "2026-05-01"},
    )
    print(f"status: {status}")
    dump(resp)

# ─── 4b. read state back, locate probe item + UID ──────────────────────────

hr("4b. GET /api/states/<target> (find probe item)")
status, state = request("GET", "/api/states/" + target_entity)
print(f"status: {status}")
probe_item: dict | None = None
if isinstance(state, dict):
    items = (state.get("attributes") or {}).get("items") or []
    print(f"total items on list: {len(items)}")
    matches = [
        it
        for it in items
        if isinstance(it, dict) and it.get("summary") == PROBE_MARKER
    ]
    if matches:
        probe_item = matches[0]
        print("probe item:")
        dump(probe_item)
    else:
        print("probe item not found; here are the first 3 items:")
        dump(items[:3])

# ─── 4c. update_item ──────────────────────────────────────────────────────

if probe_item and probe_item.get("uid"):
    hr(f"4c. POST /api/services/todo/update_item (by uid={probe_item['uid']})")
    status, upd = request(
        "POST",
        "/api/services/todo/update_item?return_response=true",
        {
            "entity_id": target_entity,
            "item": probe_item["uid"],
            "rename": PROBE_MARKER + "-updated",
            "status": "completed",
            "due_date": "2026-05-15",
        },
    )
    print(f"status: {status}")
    dump(upd)

    status, state = request("GET", "/api/states/" + target_entity)
    if isinstance(state, dict):
        items = (state.get("attributes") or {}).get("items") or []
        updated = [it for it in items if it.get("uid") == probe_item["uid"]]
        print("\nafter update, matching item(s):")
        dump(updated)
else:
    hr("4c. SKIPPED (no uid captured)")
    print("The add_item step didn't yield a UID via state readback; the UID may")
    print("not be exposed on this todo platform. This is important for our mapping.")

# ─── 4d. remove_item (cleanup) ────────────────────────────────────────────

hr("4d. POST /api/services/todo/remove_item (cleanup)")
remove_key_uid = probe_item["uid"] if (probe_item and probe_item.get("uid")) else None
for key_desc, key in (
    ("uid", remove_key_uid),
    ("original summary", PROBE_MARKER),
    ("updated summary", PROBE_MARKER + "-updated"),
):
    if not key:
        continue
    status, r = request(
        "POST",
        "/api/services/todo/remove_item",
        {"entity_id": target_entity, "item": key},
    )
    print(f"  remove by {key_desc}: status={status}")

# Verify cleanup
status, state = request("GET", "/api/states/" + target_entity)
if isinstance(state, dict):
    items = (state.get("attributes") or {}).get("items") or []
    remaining = [
        it
        for it in items
        if isinstance(it, dict)
        and it.get("summary", "").startswith(PROBE_MARKER)
    ]
    print(f"\nremaining probe items after cleanup: {len(remaining)}")
    if remaining:
        dump(remaining)

# ─── 5. fire a test event ────────────────────────────────────────────────

hr("5. POST /api/events/family_chores_probe")
status, ev = request(
    "POST",
    "/api/events/family_chores_probe",
    {"source": "family-chores probe", "ok": True},
)
print(f"status: {status}")
dump(ev)

hr("done")
print("Paste this entire output back to Claude.")
print("Revoke the LLAT when you're finished.")
