# Family Chores — Monorepo Refactor Prompt (Phase 2)

You are refactoring the existing repo at `japatton/family-chores` into a monorepo that supports three deployment targets (HA add-on today, cloud SaaS + web app tomorrow, mobile app later) from one codebase. This prompt covers **only** the refactor — no new user-facing features, no SaaS implementation, no payments, no mobile. Read the entire document before touching any file. Append every non-trivial decision to `DECISIONS.md` under a new `## 11. Monorepo refactor` section with dated entries.

---

## 0. Context you already have

You built this repo over 8 milestones ending 2026-04-22. Current state:

- **Architecture:** HA add-on, single Docker container, FastAPI + SQLAlchemy + Alembic backend, React 18 + Vite SPA frontend, Lit Lovelace card. SQLite source of truth, one-way mirror to HA entities.
- **Tests:** 243 passing (218 backend pytest + 25 frontend vitest).
- **CI:** `ci.yml` (backend + frontend + card) + `release.yml` (multi-arch GHCR builds via QEMU).
- **Design rules that must survive this refactor:** decisions #21–#28 (DB conventions), #29–#33 (rollover/streaks/timezone), #34–#38 (auth/WS/errors), #39–#46 (HA bridge), #47–#59 (frontend).

All of these decisions stay valid. This refactor is purely structural — we are moving code, not rewriting it. If a test breaks, the refactor broke it; fix the refactor, not the test.

---

## 1. Goals (what success looks like)

1. The repo becomes a monorepo with clearly-separated shared packages and thin deployment-target apps.
2. Domain logic, data model, and API routes live in shared packages that have **zero HA-specific dependencies**.
3. HA-specific code (Supervisor client, Ingress header trust, HA bridge, Lovelace card, `config.yaml`, add-on Dockerfile) is quarantined to `apps/addon/`.
4. Every DB table gains a nullable `household_id` column so multi-tenancy can be added later without another migration earthquake.
5. An **auth strategy abstraction** replaces the hardcoded Ingress-header dependency, with `IngressAuthStrategy` as the only implementation for now.
6. Empty scaffolds for `apps/saas-backend/` and `apps/web/` exist with their own package manifests and minimal smoke tests, but contain no real logic yet.
7. All 243 existing tests still pass. The add-on Docker image still builds. The Ingress UI still works end-to-end against a real HA 2026.4.x instance.
8. CI is restructured to lint/test/build per-app and per-package, in parallel where possible.

**Explicit non-goals for this prompt:**

- No SaaS backend logic. No JWT issuance flow, no Stripe, no RevenueCat, no parental consent forms. Scaffolds only.
- No mobile app directory. That's a future prompt.
- No changes to user-facing behavior of the add-on. The UI, the HA bridge, the Lovelace card, the Ingress auth flow, the parent-PIN flow — all identical from a user's perspective.
- No new features. Not even small ones. If you catch yourself thinking "while I'm in here I should also…" — stop and add it to a new `TODO_POST_REFACTOR.md` file instead.
- No rename of the project, product, or package. The Python package stays `family_chores`. The add-on slug stays `family_chores`. Branding comes later.

---

## 2. Target monorepo layout

```
/
├── pyproject.toml                # uv workspace root
├── uv.lock
├── pnpm-workspace.yaml           # pnpm workspaces root
├── package.json                  # root package.json with workspace scripts
├── repository.yaml               # HA add-on repo metadata (stays at root)
├── README.md
├── DECISIONS.md                  # existing; add §11 for this refactor
├── PROMPT.md                     # existing, don't overwrite — add this prompt
│                                 # as PROMPT_PHASE2.md instead
├── TODO_POST_REFACTOR.md         # new; drift-catcher for "while I'm here" ideas
├── .github/workflows/            # restructured — see §8
├── scripts/                      # updated for new layout
│
├── packages/                     # SHARED code, imported by apps/
│   ├── core/                     # pure domain logic (was backend/src/family_chores/core/)
│   │   ├── pyproject.toml
│   │   ├── src/family_chores_core/
│   │   │   ├── __init__.py
│   │   │   ├── recurrence.py
│   │   │   ├── instances.py
│   │   │   ├── streaks.py
│   │   │   ├── points.py
│   │   │   └── time.py
│   │   └── tests/
│   │
│   ├── db/                       # SQLAlchemy models + Alembic
│   │   ├── pyproject.toml
│   │   ├── alembic.ini
│   │   ├── src/family_chores_db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # engine/session factory (accepts URL param)
│   │   │   ├── models.py         # now includes household_id everywhere
│   │   │   ├── pragmas.py        # SQLite PRAGMA event hooks (reusable)
│   │   │   └── migrations/
│   │   │       ├── env.py
│   │   │       └── versions/
│   │   │           ├── <existing migrations, unchanged>
│   │   │           └── <NEW migration: add household_id columns>
│   │   └── tests/
│   │
│   └── api/                      # FastAPI routers + services
│       ├── pyproject.toml
│       ├── src/family_chores_api/
│       │   ├── __init__.py
│       │   ├── app.py            # FastAPI factory taking deps injected
│       │   ├── routers/          # members, chores, instances, auth, admin, ws, health
│       │   ├── services/         # DB-orchestrating code (moved from backend/services/)
│       │   ├── schemas/          # Pydantic DTOs
│       │   ├── deps/             # dependency injection
│       │   │   ├── __init__.py
│       │   │   ├── auth.py       # AuthStrategy ABC + IngressAuthStrategy impl
│       │   │   ├── db.py         # session dep
│       │   │   └── tenant.py     # get_current_household_id dep (ties to AuthStrategy)
│       │   ├── errors.py         # global error envelope (moved verbatim)
│       │   └── ws.py             # WebSocket broadcast (moved verbatim)
│       └── tests/
│
└── apps/                         # DEPLOYMENT TARGETS, thin
    ├── addon/                    # the HA add-on (was family_chores/ at repo root)
    │   ├── config.yaml
    │   ├── Dockerfile
    │   ├── build.yaml
    │   ├── run.sh
    │   ├── icon.png, logo.png
    │   ├── DOCS.md
    │   ├── CHANGELOG.md
    │   ├── pyproject.toml        # depends on packages/core, /db, /api via workspace
    │   ├── src/family_chores_addon/
    │   │   ├── __main__.py       # uvicorn entrypoint, was __main__.py
    │   │   ├── app_factory.py    # wires AuthStrategy=IngressAuth, starts HA bridge
    │   │   ├── config.py         # reads /data/options.json
    │   │   ├── scheduler.py      # APScheduler jobs (addon-specific wiring)
    │   │   └── ha/               # entire HA bridge lives here, not in packages/
    │   │       ├── client.py
    │   │       ├── sync.py
    │   │       └── reconcile.py
    │   └── tests/                # addon-specific tests (HA bridge, reconcile)
    │
    ├── saas-backend/             # SCAFFOLD ONLY — do not implement
    │   ├── pyproject.toml
    │   ├── README.md             # "Placeholder. Implementation in Phase 3."
    │   ├── src/family_chores_saas/
    │   │   ├── __init__.py
    │   │   └── app_factory.py    # minimal: creates app with PlaceholderAuthStrategy
    │   │                         # that returns 501 Not Implemented for everything
    │   └── tests/
    │       └── test_smoke.py     # asserts app starts and /health returns 200
    │
    └── web/                      # SCAFFOLD ONLY — do not implement
        ├── package.json
        ├── README.md             # "Placeholder. Implementation in Phase 3."
        ├── vite.config.ts
        ├── tsconfig.json
        ├── index.html
        ├── src/
        │   └── main.tsx          # renders a "Coming soon" placeholder
        └── tests/

# Remaining top-level (unchanged function, may move):
├── lovelace-card/                # stays where it is — not part of any app
└── frontend/                     # MOVED to apps/addon/frontend/ (Ingress SPA)
```

### Notes on the layout

- **`apps/addon/frontend/`** — the Ingress SPA moves inside the add-on, because it's only ever shipped by the add-on. When `apps/web/` grows up it will share components via a future `packages/ui/` — not this prompt's job. For now the add-on frontend stays exactly where it is, just relocated.
- **`lovelace-card/`** stays at the root. It's not an app, it's a separate HA artifact. Keeping it visible prevents it from getting forgotten under `apps/addon/`.
- **Python package names are `family_chores_core`, `family_chores_db`, `family_chores_api`, `family_chores_addon`, `family_chores_saas`** — no leading `src.` or `backend.`. Pick these names once and stick to them. Update every import accordingly.
- **The Supervisor token, the `http://supervisor/core` URL, the Ingress header names (`X-Ingress-Path`, `X-Remote-User`), and anything in the `ha/` directory are all add-on concerns only.** They must not appear anywhere under `packages/`.

---

## 3. The auth strategy abstraction (critical detail — get this right)

Right now, `packages/api`-to-be has identity resolution hardcoded to Ingress headers. Change this to a strategy pattern so the same routers can be mounted in the add-on (trusting Ingress) or in the SaaS (trusting a JWT from Supabase Auth, Clerk, or whatever we pick in Phase 3) without any change to the routers themselves.

```python
# packages/api/src/family_chores_api/deps/auth.py

class AuthStrategy(Protocol):
    async def identify(self, request: Request) -> Identity: ...
    async def require_parent(self, request: Request) -> ParentIdentity: ...

@dataclass
class Identity:
    user_key: str           # stable identifier; "anonymous" for add-on anon fallback
    household_id: str | None  # None in add-on single-tenant mode
    is_parent: bool         # did this request pass parent-elevation?
```

Then `IngressAuthStrategy` (in `apps/addon/`) implements this by reading `X-Remote-User` + the in-memory parent-JWT check; the future `JWTAuthStrategy` (in `apps/saas-backend/`, Phase 3) will verify a bearer token from the SaaS identity provider.

**The key rule:** every query in `packages/api/services/` that touches tenant-scoped data takes `household_id` as a parameter and filters by it. If `household_id is None` (add-on mode), the query runs unscoped (matching today's behavior). If `household_id is not None` (SaaS mode, future), the query is strictly scoped. This means the service layer already has multi-tenancy plumbing by the end of this prompt, even though no caller is multi-tenant yet.

Add a pytest fixture `scoped_session_for_household(household_id)` that you use in new tests to verify scoping works both ways.

---

## 4. The household_id migration

Write **one** new Alembic migration that:

1. Adds a nullable `household_id VARCHAR(36)` column to: `member`, `chore`, `chore_assignment`, `chore_instance`, `member_stats`, `activity_log`, `app_config`.
2. Adds an index on `household_id` on each of those tables.
3. Does **not** backfill existing rows — they stay NULL (which is the correct value for single-tenant add-on mode).
4. Does **not** make the column NOT NULL. That's a future migration after the SaaS is real and every row has a real household.
5. Updates every query in `packages/api/services/` to accept an optional `household_id: str | None` parameter and apply a `WHERE household_id IS NOT DISTINCT FROM :household_id` clause (in raw SQL terms; the SQLAlchemy-ism is `column.is_(None)` vs `column == value` depending on input).

**Important:** SQLite treats `NULL = NULL` as false, so use `IS NOT DISTINCT FROM` semantics explicitly. SQLAlchemy's way is `Member.household_id.is_(None)` when the param is None, else `Member.household_id == household_id`. Write a helper `scoped(col, value)` that returns the right clause; use it everywhere.

Add tests that verify:

- When `household_id=None`, all existing rows are returned (add-on mode unchanged).
- When `household_id="abc"`, only rows with that value are returned.
- Rows created without a `household_id` keep NULL (add-on path).
- Rows created with a `household_id` get that value.

---

## 5. Tooling: uv workspace + pnpm workspace

### Python (uv workspace)

Root `pyproject.toml`:

```toml
[tool.uv.workspace]
members = ["packages/core", "packages/db", "packages/api", "apps/addon", "apps/saas-backend"]

[tool.uv.sources]
family-chores-core = { workspace = true }
family-chores-db = { workspace = true }
family-chores-api = { workspace = true }
```

Each `packages/*/pyproject.toml` declares its own deps; `apps/addon/pyproject.toml` declares `family-chores-core`, `family-chores-db`, `family-chores-api` as workspace deps plus its add-on-only deps (httpx for Supervisor client, etc.).

**Run everything with `uv sync` and `uv run`.** Drop Poetry if present. Update `scripts/lint.sh` and CI accordingly.

### Frontend (pnpm workspace)

Root `pnpm-workspace.yaml`:

```yaml
packages:
  - "apps/addon/frontend"
  - "apps/web"
  - "lovelace-card"
```

Root `package.json` has `scripts.build = "pnpm -r build"`, etc. Each frontend package keeps its own `vite.config.ts` / `rollup.config.mjs`.

**Don't hoist aggressively.** Each frontend has its own `node_modules` for now; we'll introduce shared UI later.

---

## 6. The Dockerfile migration

The current add-on Dockerfile has a single multi-stage build that copies `backend/` + `frontend/` and builds both. After this refactor, the Dockerfile lives at `apps/addon/Dockerfile` and must:

1. Copy the full monorepo into the build context (needed because it must install `packages/core`, `/db`, `/api` as workspace members).
2. Use `uv sync --frozen --package family-chores-addon` to install exactly the add-on's dep tree including workspace packages.
3. Build the frontend from `apps/addon/frontend/` via pnpm.
4. Copy the built SPA into `apps/addon/src/family_chores_addon/static/` (same location as today, just under the new path).
5. Produce an image that boots identically to today's — same port, same Ingress behavior, same `/data` volume use.

The image must continue to work on HA OS 2026.4.x without any user action beyond reinstalling the add-on. Document the upgrade path in `apps/addon/CHANGELOG.md`.

---

## 7. Testing requirements

1. **All 218 existing backend tests pass unchanged** — only their import paths change (`from family_chores.core.*` → `from family_chores_core.*`, etc.).
2. **All 25 existing frontend tests pass unchanged.**
3. **New tests** added for:
   - The auth strategy abstraction (fake strategy that returns a fixed household_id, verify routes scope correctly).
   - The `scoped()` helper (None → all rows, value → filtered rows).
   - The new household_id migration (up/down, data preserved).
   - `apps/saas-backend/tests/test_smoke.py` — app starts, `/health` returns 200, everything else returns 501.
   - `apps/web/tests/` — placeholder renders.
4. **An integration test** that builds the add-on Docker image in CI and boots it against a fake Supervisor stub, hits `/api/info`, and verifies `ha_connected` and a couple of endpoints. This is new; add it to `ci.yml`.

Total test count after this prompt should be roughly 260+ — the existing 243 plus ~20 new. If it's dramatically higher, you've scope-crept.

---

## 8. CI restructure

Replace `ci.yml` with a matrix that runs per-workspace-member in parallel:

- `lint-python` — ruff + mypy --strict across all `packages/*` and `apps/addon`, `apps/saas-backend`.
- `test-core`, `test-db`, `test-api` — pytest per package.
- `test-addon` — pytest for `apps/addon/tests/`.
- `test-saas` — smoke tests for the scaffold.
- `lint-frontend` — eslint + tsc across `apps/addon/frontend`, `apps/web`, `lovelace-card`.
- `test-frontend` — vitest for each frontend package.
- `build-addon-frontend` — produces SPA artifact.
- `build-card` — produces bundled JS.
- `build-addon-image` — full Docker build for amd64 on PR (aarch64/armv7 only on tag, unchanged).
- `integration-addon` — new; boots image against fake Supervisor.

`release.yml` updates paths and nothing else.

---

## 9. Migration sequence (how to actually do this without breaking everything)

Do this in exactly this order. Commit after each step. Each commit must have a green CI run.

1. **Scaffold the empty `packages/` and `apps/` directories with `__init__.py` files and stub `pyproject.toml`s.** No code yet. Verify `uv sync` works.
2. **Move `core/` into `packages/core/`**, update the handful of its imports, add a package-level test that imports from it. Verify tests still pass.
3. **Move `db/` into `packages/db/`** including the Alembic migrations. This is the riskiest move — keep the same migration version hashes; add only the path change. Run the existing test suite against the moved package to confirm nothing broke.
4. **Move `api/` routers, services, schemas, WS, errors into `packages/api/`** but keep Ingress auth in place as a concrete class in `packages/api/deps/auth.py` temporarily (just renamed, not yet abstracted).
5. **Introduce the AuthStrategy abstraction** in `packages/api/deps/auth.py`. Move the Ingress implementation to `apps/addon/src/family_chores_addon/auth.py`. Add a test that `packages/api` contains no reference to "supervisor", "ingress", or HA headers.
6. **Move the add-on top-level into `apps/addon/`.** Dockerfile, config.yaml, run.sh, HA bridge, scheduler, options-reader, `app_factory.py` that wires everything up. Update `repository.yaml` if the path changed.
7. **Move the Ingress SPA into `apps/addon/frontend/`.** Update the Dockerfile's build stage paths. Verify the Docker build still succeeds.
8. **Write the new household_id migration.** Run it against a copy of a real `.storage` DB if you have one handy; confirm no data loss and NULLs everywhere.
9. **Update every service query to use the `scoped()` helper** and take optional `household_id`. The add-on always passes `None`. Tests should cover both paths.
10. **Scaffold `apps/saas-backend/`** with `PlaceholderAuthStrategy` that returns 501 on `identify()` and a single `/health` endpoint.
11. **Scaffold `apps/web/`** with a Vite project that renders "Coming soon".
12. **Restructure CI** into the matrix described in §8. Ensure the happy path builds and tests everything in parallel and the total CI wall-clock time is no worse than today.
13. **Write §11 of `DECISIONS.md`** capturing every deviation from this prompt and every surprise encountered. Reference specific commit hashes per step, matching the §10 pattern.

---

## 10. Drift prevention

**Things that will tempt you to scope-creep. Resist them and add them to `TODO_POST_REFACTOR.md` instead:**

- "While I'm updating imports I should also rename things to be more consistent."
- "The HA bridge has this one awkward thing; let me fix it while I'm moving it."
- "The Alembic env.py could be cleaner."
- "We should probably also add [feature] to prepare for the SaaS."
- "The frontend structure would be nicer if..."
- "Let me just upgrade this dep while I'm here."

None of these belong in this refactor. If you touch any of them, the PR becomes unreviewable and multi-tenancy bugs will hide in the noise. Stay narrow.

**Also:** do not change anything the user sees. The Ingress UI at the end of this refactor looks identical, behaves identically, has all the same routes, fires the same HA events, and mirrors the same entities as the start. The add-on's CHANGELOG.md gets a single line: "Internal refactor to monorepo layout. No user-facing changes."

---

## 11. Process expectations

- **Start by writing the `## 11. Monorepo refactor` section of `DECISIONS.md`** with your plan — how you'll sequence the 13 steps, what you expect to find tricky, and any clarifying questions that block you. Then pause for review.
- **Work the 13 steps in order.** After each, stop and summarize: what moved, what broke, what you fixed. Don't batch.
- **Never rewrite a test to make it pass after a move.** If a test fails after a move, the move is wrong; fix the move. The only acceptable test change in this refactor is updating import paths.
- **If you discover the HA bridge has an actual bug** (not a style nit, a bug that breaks mirroring), log it in `TODO_POST_REFACTOR.md` with reproduction steps and continue. Do not fix it in this PR.
- **If something in this prompt conflicts with a decision recorded in existing `DECISIONS.md` §1–10**, the existing decision wins and you note the tension in the new §11. Prompts are weaker than lived experience; your own commit notes outrank them.

Begin with the new `## 11. Monorepo refactor` section of `DECISIONS.md`.

---

## Deviations applied 2026-04-23 (recorded here for traceability; full rationale in DECISIONS §11)

- Add-on stays at **`family_chores/`** at the repo root (not `apps/addon/`). HA Supervisor convention puts each add-on as a direct child of the repo root; we don't want to probe deep-recursion behavior on live installs.
- Add-on Python layout is **flat**: `family_chores/pyproject.toml` + `family_chores/src/family_chores_addon/` + `family_chores/tests/`. No `backend/` wrapper.
- `pnpm-workspace.yaml` declares frontends as they migrate: `apps/web` in step 1; `family_chores/frontend` and `lovelace-card` added in step 7 (when each migrates from npm).
- `EventProtocol` in `packages/api/events.py` decouples event construction from HA-bridge delivery; dependency-arrow test enforces `apps → packages` only.
- JWT `sign()`/`verify()` take an explicit `secret` parameter (no module-level constant).
