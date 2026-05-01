# Architecture

This is the contributor-facing overview. For the running design journal with the "why" behind each decision, see [`DECISIONS.md`](../DECISIONS.md). For the user-facing "what does it do" summary, see the repo-root [`README.md`](../README.md).

## Layout

The repo is a monorepo with three tiers: shared libraries (`packages/`), deployment roots (`family_chores/` and `apps/*/`), and the Lovelace card (separate build).

```
family-chores/
├── packages/               # Shared libraries — no HA, no FastAPI app, no deployment specifics
│   ├── core/                 # Pure domain: recurrence, streaks, points math
│   ├── db/                   # SQLAlchemy models + Alembic + scoped() helper
│   └── api/                  # Router protocols + auth primitives
│
├── family_chores/          # THE HOME ASSISTANT ADD-ON (the shipped artefact)
│   ├── config.yaml           # HA add-on manifest
│   ├── Dockerfile            # Multi-stage: Node for frontend, Python for backend
│   ├── build.yaml            # Multi-arch base-image pins
│   ├── frontend/             # React 18 + TS + Vite + Tailwind + Zustand SPA
│   └── src/family_chores_addon/   # Thin composition root: wires packages/* into an HA add-on
│
├── apps/                   # Other deployment targets (composition roots)
│   ├── saas-backend/         # SaaS scaffold (FastAPI + Postgres-ready) — not shipped
│   └── web/                  # Web placeholder SPA — not shipped
│
├── lovelace-card/          # Read-only HA dashboard widget (Lit + Rollup → single-file JS)
│
├── docs/                   # Contributor-facing documentation
├── scripts/                # dev_backend.sh, dev_frontend.sh, lint.sh
└── tests/                  # Architecture tests (dependency arrows + packages-clean)
```

Everything under `packages/` is generic enough to be reused across deployment targets. Everything under `family_chores/` or `apps/*/` is a composition root — it picks concrete implementations and wires them into a running app.

## Dependency direction

The core rule: **apps and add-ons depend on packages. Packages never depend on apps, and no package depends on another package's deployment-specific implementation.**

```
       packages/core
        ↑        ↑
        │        │
   packages/db   │
        ↑        │
        │        │
        └── packages/api
                 ↑
   ┌─────────────┼──────────────┐
   │             │              │
family_chores  apps/saas    apps/web
               -backend
```

This is enforced by two CI tests:

- **`tests/test_dependency_arrows.py`** — reads every package's `pyproject.toml` and verifies the `dependencies:` list doesn't violate the arrow. `packages/core` can depend on nothing in this tree. `packages/db` can depend on `packages/core`. `packages/api` can depend on both. Nothing in `packages/*` can import `family_chores_addon` or anything under `apps/`.
- **`tests/test_packages_clean.py`** — greps `packages/` for HA-specific strings (`homeassistant`, `SUPERVISOR_TOKEN`, `hassio`, etc.) and fails if any leak in.

Both tests run in CI on every PR. Violate the arrow and CI fails before review starts.

## The three deployment roots

### `family_chores/` — the Home Assistant add-on

This is the one that actually ships. It's a composition root that:

1. Imports the domain, DB, and API layers from `packages/*`.
2. Provides HA-specific implementations of the abstract bits:
   - `IngressAuthStrategy` — trusts HA Supervisor's `X-Remote-User` header on Ingress requests.
   - `HAClient` — async httpx wrapper that picks `SUPERVISOR_TOKEN` (add-on runtime) or `HA_URL + HA_TOKEN` (local dev).
   - `HABridge` — debounces DB deltas into HA entity updates and fires events.
3. Mounts the built React SPA and serves it at the Ingress path.

The built image is published to GHCR (`ghcr.io/japatton/family-chores-{arch}`) on every tagged release. HA Supervisor pulls that image directly — it doesn't build locally.

### `apps/saas-backend/` — SaaS scaffold (not shipped)

A parallel composition root that demonstrates the `packages/` → `apps/` pattern can retarget from "single-tenant add-on inside HA" to "multi-tenant web service behind a load balancer." Uses the same `packages/core` domain logic and the same `packages/db` models, but replaces `IngressAuthStrategy` with a JWT-based `PlaceholderAuthStrategy` and scopes every query by `household_id` via the `scoped(col, value)` helper in `packages/db`.

Not a current deployment target. It exists to prove the abstractions hold. See [`DECISIONS.md`](../DECISIONS.md) for the tenancy design.

### `apps/web/` — placeholder web frontend (not shipped)

React + Vite placeholder for "what would a standalone web UI look like." Non-functional at present; exists so the frontend tooling matrix (pnpm workspace, shared tsconfig) has more than one node in it.

## Authentication strategies

`packages/api/src/family_chores_api/deps/auth.py` defines an `AuthStrategy` Protocol:

```python
class AuthStrategy(Protocol):
    async def authenticate_request(self, request: Request) -> ParentClaim | None: ...
    async def issue_parent_token(self, household_id: str, pin: str) -> str: ...
    async def refresh_parent_token(self, token: str) -> str: ...
```

Three implementations in the tree:

| Implementation | Where it lives | Used by |
|---|---|---|
| `IngressAuthStrategy` | `family_chores/src/family_chores_addon/auth.py` | The shipped add-on — trusts Supervisor's `X-Remote-User` header |
| `PlaceholderAuthStrategy` | `apps/saas-backend/src/.../auth.py` | SaaS scaffold smoke tests |
| `FakeAuthStrategy` | `packages/api/tests/conftest.py` | Router-level unit tests in the shared package |

Routers under `packages/api/` depend only on the Protocol. Swapping strategies requires changing zero imports in the shared code.

## Provider Protocols (HA-decoupling seam)

The same Protocol pattern decouples the addon's HA-specific subsystems from the shared service layer. Today there are two:

| Protocol | Defined in | HA impl | NoOp impl |
|----------|------------|---------|-----------|
| `CalendarProvider` | `packages/api/services/calendar/provider.py` | `family_chores/.../ha/calendar.py` (`HACalendarProvider`) | `NoOpCalendarProvider` (same module) |
| `TodoProvider` | `packages/api/services/todo/provider.py` | `family_chores/.../ha/todo.py` (`HATodoProvider`) | `NoOpTodoProvider` (same module) |

The composition service (`packages/api/services/calendar/service.py`) and the bridge / reconciler (`family_chores/.../ha/bridge.py`, `.../ha/reconcile.py`) depend only on the Protocols. The addon's lifespan (`family_chores_addon/app.py`) constructs the HA-backed implementations once at startup; the SaaS scaffold (`apps/saas-backend/src/.../app_factory.py`) constructs the no-op variants. Routers + services don't know which is plugged in.

This is the seam Tier 2 of the [DECISIONS §14 decoupling roadmap](../DECISIONS.md) builds on: a future standalone Docker target swaps in a CalDAV / Google Calendar / Microsoft Calendar provider without touching the bridge or service code.

See [`docs/calendar.md`](calendar.md) for the calendar-specific shape.

## Tenancy

All tenant-scoped tables in `packages/db/` carry a `household_id: str` column. Every query in the shared layer uses the `scoped(col, value)` helper:

```python
stmt = select(Member).where(scoped(Member.household_id, household_id))
```

For the add-on, `household_id` is a single synthetic constant (`"default"`); the multi-tenant plumbing is dormant. For `apps/saas-backend`, it comes from the authenticated JWT claim and every query is scoped by it. This is why the shared package passes a "no single-tenant assumptions" review: it's structurally difficult to write a query in `packages/` that accidentally leaks cross-household data.

## Data flow (add-on)

```
Kid taps "Done"
      ↓
React SPA → POST /api/instances/:id/complete
      ↓
packages/api service → packages/db (SQLite write)
      ↓
Mutation event → HABridge backlog (500 ms debounce window)
      ↓
Batched update → HAClient → Supervisor proxy → HA state machine
      ↓
sensor.family_chores_alice_points          ← updated
sensor.family_chores_pending_approvals     ← updated (if requires_approval)
todo.alice_chores                          ← item flipped to complete (if HA todo linked)
```

SQLite is the source of truth. HA entity state is a read-only mirror. The add-on never reads state from HA to make decisions — it only writes.

See [`DECISIONS.md`](../DECISIONS.md) for the full data-flow diagram and the reasoning behind the one-way-write choice.

## Testing topology

Tests live next to the code they cover:

| Directory | Count | What it covers |
|---|---|---|
| `packages/core/tests` | 57 | Pure domain logic (recurrence, streaks, points math) |
| `packages/db/tests` | 37 | ORM, Alembic migrations, `scoped()` helper |
| `packages/api/tests` | 2 | `FakeAuthStrategy` fixture smoke |
| `family_chores/tests` | 147 | Add-on integration (routers, services, HA bridge, lifespan) |
| `apps/saas-backend/tests` | 12 | SaaS scaffold smoke |
| `tests/` (repo root) | 81 | Architecture (dep-arrows + packages-clean) |
| `family_chores/frontend` | 26 (vitest) | React SPA stores, client, components |
| `apps/web` | 2 (vitest) | Web placeholder smoke |

Total: **364 tests**, all green on every PR. `./scripts/lint.sh` runs the whole matrix (lint + typecheck + tests) locally in ~15 seconds.

## Release topology

- **Git tags** matching `v*.*.*` trigger `.github/workflows/release.yml`.
- The workflow builds three architectures (`linux/amd64`, `linux/arm64`, `linux/arm/v7`) via `docker/setup-qemu-action` + `docker/build-push-action@v6` and pushes to `ghcr.io/japatton/family-chores-{arch}`.
- A fan-in `publish-release` job attaches the Lovelace-card JS to the matching GitHub release so `release.yml` has a one-stop artefact drop.
- HA Supervisor's update flow pulls the matching `:X.Y.Z` image directly — no local compile.

SQLite data at `/data/family_chores.db` is preserved across updates because the add-on slug stays `family_chores` regardless of internal layout changes.

## Where to read next

- [`DECISIONS.md`](../DECISIONS.md) — every non-obvious choice, with dates and rationale.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — dev setup, per-package test commands, and PR expectations.
- [`docs/roadmap.md`](roadmap.md) — what's planned, what's on the radar, what's out of scope.
