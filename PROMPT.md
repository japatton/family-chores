# Family Chores — Home Assistant Add-on Build Prompt

You are building **Family Chores**, a Home Assistant **Add-on** (Supervisor-managed Docker container) with a web UI served via HA Ingress, plus an optional thin Lovelace card for at-a-glance dashboard display. Read this entire document before writing any code. Where anything is ambiguous, prefer the option that is simpler to maintain, closer to HA Add-on conventions, and matches the data-flow rules in Section 4. Record every meaningful design decision in `DECISIONS.md`.

---

## 1. Target environment (hard constraints)

- **Home Assistant OS** with Supervisor. Install path will be the "local add-ons" folder (`/addons/family_chores/` on the host) or a custom add-on repository.
- Minimum HA version: **2024.10**. Use `todo` platform features introduced in 2024.1+ (items with `due` surface on the calendar automatically).
- The add-on is a **single Docker container**:
  - Base image: `ghcr.io/home-assistant/{arch}-base-python:3.12-alpine3.20`. Build for **aarch64, amd64, armv7**.
  - Runs a **FastAPI** app (uvicorn, single worker) on port 8099 inside the container.
  - **Ingress enabled** (`ingress: true`, `ingress_port: 8099`) — no host port exposed by default. Users must not have to open a LAN port or set up a reverse proxy.
- Data persisted to `/data` (the Supervisor-mounted persistent volume): **SQLite** at `/data/family_chores.db`, rotating backup at `/data/family_chores.db.bak` written before each Alembic migration.
- HA communication uses the **Supervisor proxy**. The env vars `SUPERVISOR_TOKEN` and the hostname `supervisor` are provided automatically. Talk to HA at `http://supervisor/core/api/...` with `Authorization: Bearer $SUPERVISOR_TOKEN`. **Do not ask the user for a long-lived access token.**
- Required `config.yaml` permissions: `hassio_api: true`, `hassio_role: default`, `homeassistant_api: true`, `auth_api: true`, `ingress: true`. Justify any additions in `DECISIONS.md`.
- Primary display target: **wall-mounted tablet**, landscape, ~10" @ 1280×800, touch-only. UI must also be usable on phone (HA companion app opens Ingress) and desktop, but tablet is the design target.

---

## 2. Deliverables

```
family-chores/
├── config.yaml                   # HA add-on manifest
├── Dockerfile
├── build.yaml                    # multi-arch base image map
├── run.sh                        # entrypoint (no s6 needed for single process)
├── icon.png, logo.png            # placeholders OK
├── README.md
├── CHANGELOG.md
├── DOCS.md                       # shown in the add-on Documentation tab
├── INSTALL.md                    # how to add repo, install, configure
├── DECISIONS.md                  # your running design notes
├── PROMPT.md                     # copy of this prompt
├── backend/
│   ├── pyproject.toml
│   ├── src/family_chores/
│   │   ├── __main__.py           # uvicorn entrypoint
│   │   ├── app.py                # FastAPI app factory
│   │   ├── api/                  # routers: members, chores, instances, auth, admin, ws
│   │   ├── core/                 # pure domain logic (recurrence, streaks, points)
│   │   ├── db/                   # SQLAlchemy models + Alembic migrations
│   │   ├── ha/                   # Supervisor client + entity-sync service
│   │   ├── scheduler.py          # APScheduler jobs (midnight rollover, sync)
│   │   ├── config.py             # reads /data/options.json
│   │   └── static/               # built SPA is copied here at image build time
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── src/                      # React 18 + TypeScript SPA
│   └── index.html
├── lovelace-card/
│   ├── package.json
│   └── src/family-chores-card.ts # Lit card that reads HA entities (optional UI surface)
├── scripts/
│   ├── dev_backend.sh
│   ├── dev_frontend.sh
│   └── lint.sh
└── .github/workflows/            # build multi-arch, run tests, lint
```

The Ingress web app is the primary UI. The Lovelace card is a secondary surface for users who want a chore widget on a main HA dashboard; it must not be required for the add-on to be useful.

---

## 3. Feature scope for v1

### In scope

- **Family members** (unlimited). Fields: `name`, `slug`, `avatar` (emoji OR uploaded image stored under `/data/avatars/`), `color`, `display_mode` (`kid_large` | `kid_standard` | `teen`), `requires_approval` (bool).
- **Chores**: `name`, `icon` (emoji or `mdi:*`), `points`, `assigned_member_ids` (one or many), `recurrence` (see below), `time_window` (optional `{start, end}` local times), `description`, `image` (optional), `active` flag.
- **Recurrence rules**, evaluated server-side in the user's configured timezone:
  - `daily`
  - `weekdays` (Mon–Fri)
  - `weekends`
  - `specific_days` (ISO weekday ints, 1=Mon)
  - `every_n_days` with anchor date
  - `monthly_on_date` (1–31; shorter months clamp to last day)
  - `once` (specific date)
- **Chore instances** — one per `(chore, member, date)`. States: `pending`, `done_unapproved`, `done`, `skipped`, `missed`. Generated up to **14 days ahead**. At local midnight, unresolved `pending`/`done_unapproved` from the previous day become `missed`.
- **Parent approval flow** — when a member has `requires_approval=true`, tapping Complete sets state to `done_unapproved`. Points are not awarded until a parent calls `approve`. Parent can also `reject` with reason (reverts to `pending`) or award/deduct manually.
- **Points and streaks**:
  - Lifetime points total per member + points-this-week (week starts on configured weekday, default Monday).
  - Streak = consecutive days where 100% of that member's assigned instances ended in `done` (approved). A day with zero assigned chores does not break or extend a streak.
  - Streak milestones fire HA events at 3, 7, 14, 30, 100.
- **Parent mode** — 4-digit PIN, stored hashed (argon2). README must state explicitly this is a soft lock to keep kids out, not a security boundary; real access control is HA's own auth. PIN unlock lasts 5 minutes of inactivity on that browser session.
- **Kid-engagement UI**:
  - **Today view** as landing: grid of member tiles, each showing avatar, progress ring (% complete today), streak, points-this-week. Tap tile → member view.
  - **Member view**: large chore cards, one tap to complete, 4-second undo toast, confetti + optional chime on completion, "⏳ Waiting for parent" badge when `done_unapproved`.
  - **Parent view** (behind PIN): approval queue, add/edit/delete members and chores, manual point adjustments, view recent activity log.
  - Tap targets min 72px, high contrast, no hover-only affordances, subtle slow background shift to reduce tablet burn-in, per-member accent color themes their screen.
  - Celebratory empty state when a member finishes their day.

### Explicitly out of scope for v1 (mention in README under "Future")

- Redeemable reward catalog (points → real-world rewards).
- Per-kid PIN/profile lock (v1 is honor system).
- Voice/TTS announcements.
- Photo-proof of completion.
- Multi-household sync.

Do not build these. If the architecture makes a future addition trivial, note the hook point in `DECISIONS.md`.

---

## 4. Data flow rules (read this twice)

**SQLite is the source of truth.** HA entities are a one-way read-only mirror maintained by the add-on. Never read state *from* HA in order to decide business logic — always read from SQLite. This rule exists to prevent drift and race conditions.

Flow:

```
   ┌────────────────────┐   HTTP (Ingress)   ┌──────────────┐
   │  Browser / SPA     │ <─────────────────>│  FastAPI     │
   │  (parents + kids)  │                    │  backend     │
   └────────────────────┘                    │              │
                                             │  SQLite ◄── source of truth
                                             │              │
                                             │  ha/sync.py  │
                                             └──────┬───────┘
                                                    │ HA REST API
                                                    │ via http://supervisor/core
                                                    ▼
                                        ┌───────────────────────┐
                                        │  HA entities (mirror) │
                                        │  sensor.*_points      │
                                        │  sensor.*_streak      │
                                        │  sensor.pending_appr. │
                                        │  todo.family_chores_* │
                                        └───────────────────────┘
                                                    ▲
                                                    │ reads only
                                                    │
                                        ┌───────────────────────┐
                                        │  Lovelace card        │
                                        │  (optional dashboard) │
                                        └───────────────────────┘
```

**The HA bridge** (`ha/sync.py`) must:
- On every write to SQLite that changes observable state, enqueue a sync task. Debounce bursts (e.g. 500ms) to avoid hammering HA.
- Use HA's REST API to:
  - Publish/update sensor state via `POST /api/states/sensor.family_chores_<slug>_points` with attributes `{points_this_week, streak, today_progress_pct, member_id}`.
  - Publish `sensor.family_chores_<slug>_streak`.
  - Publish `sensor.family_chores_pending_approvals` globally.
  - Manage todo items on one `todo.family_chores_<slug>` per member by calling the `todo.add_item` / `todo.update_item` / `todo.remove_item` services. Each chore instance with a due date/time maps to a todo item; HA surfaces those on its calendar automatically. Use a stable mapping (store the HA todo item UID in SQLite).
- On startup, reconcile: for each member, fetch existing todo items and align them with current instances (create missing, update changed, remove orphans).
- Fire HA events via `POST /api/events/<event_type>` for:
  - `family_chores_completed` — payload: member_id, chore_id, instance_id, points
  - `family_chores_approved` — same payload
  - `family_chores_streak_milestone` — payload: member_id, streak_days
- If HA is unreachable (startup race, brief outage), the add-on continues to function; sync retries with exponential backoff and a max per-event queue. The UI is never blocked by HA unavailability.

**What the add-on does NOT do:** register as a HA integration, create a config flow, or install anything into `/config/custom_components`. It is a pure external service that speaks to HA via the REST API only.

---

## 5. Data model (SQLAlchemy)

Tables (singular names shown; use plural in schema):

- `member(id, name, slug UNIQUE, avatar, color, display_mode, requires_approval, created_at, updated_at)`
- `chore(id, name, icon, points, description, image, active, recurrence_type, recurrence_config JSON, time_window_start, time_window_end, created_at, updated_at)`
- `chore_assignment(chore_id, member_id)` — many-to-many
- `chore_instance(id, chore_id, member_id, date, state, completed_at, approved_at, approved_by, points_awarded, ha_todo_uid, created_at, updated_at)`
  - Unique index on `(chore_id, member_id, date)`.
- `member_stats(member_id PK, points_total, points_this_week, week_anchor, streak, last_all_done_date, updated_at)` — cached aggregates, rebuildable from instances.
- `activity_log(id, ts, actor, action, payload JSON)` — append-only audit for the parent view.
- `app_config(key PK, value JSON)` — parent_pin_hash, sound_enabled_default, week_starts_on, timezone_override, etc.

Use Alembic from day one. First migration creates everything above. Before any migration runs, copy `/data/family_chores.db` to `/data/family_chores.db.bak`.

All times stored as UTC ISO-8601. All "today" logic uses the HA-reported timezone (fetched once at startup via `GET /api/config`, refreshed hourly).

---

## 6. Backend architecture

- **FastAPI** with routers split by resource. Pydantic v2 models.
- **APScheduler** for:
  - Midnight rollover job (in local tz): mark overdue, compute streaks, reset `points_this_week` on week boundary, generate tomorrow's instances, prune instances older than 90 days into a monthly summary row.
  - Periodic HA sync reconcile (every 15 min) as a safety net against missed events.
- **Auth** inside the add-on:
  - Ingress requests arrive already authenticated by HA — the `X-Ingress-Path` and `X-Remote-User` headers are set by Supervisor. Trust these for identifying the HA user.
  - Parent mode requires a second factor: the PIN. Store `parent_pin_hash` with argon2. On `POST /api/auth/verify_pin`, return a short-lived HS256 JWT (5-minute exp) scoped `role=parent`. Mutating parent endpoints require that JWT.
  - Kid-facing endpoints (list today's chores, mark complete) only require Ingress auth.
- **WebSocket** at `/api/ws` for live UI updates — on any state change, broadcast a minimal event (`instance_updated`, `member_updated`, etc.) and let the client refetch or patch. Don't try to push full snapshots.
- **Input validation**: Pydantic models on every endpoint. Reject unknown IDs with 404, not 500.
- **Logging**: structured (structlog or stdlib with JSON formatter), log level from add-on options (`debug` | `info` | `warning`). Never log PIN hashes, JWTs, or the Supervisor token.
- **Error handling**: global exception handler returns `{error, detail, request_id}`. Corrupt DB on startup → restore from `.bak` if present, else initialize empty, log loudly, set a banner flag the UI can display.

---

## 7. Frontend (Ingress SPA)

- **React 18 + TypeScript + Vite**. State management: **Zustand** (lightweight, no boilerplate). Data fetching: **TanStack Query**. Routing: **React Router**.
- Styling: **Tailwind CSS**. No component library — write the components yourself so the aesthetic matches (kid-friendly, playful, not corporate).
- Use **canvas-confetti** (npm) for completion animation. Bundle a small completion chime as an OGG in `src/assets/`, played only if sound is enabled.
- **Ingress-aware**: fetch URLs must be relative (the Ingress path is variable). Never hardcode `http://homeassistant.local:...`.
- **Offline tolerance**: TanStack Query keeps last-known data on screen; show a small "reconnecting…" pill if the WebSocket drops. Never blank the UI.
- **Accessibility**: keyboard navigable, ARIA labels, min contrast AA. Even on a kid tablet, this matters.
- **PWA-ish**: include a manifest and icons so it can be added to a tablet home screen, but don't register a service worker (Ingress + service workers is a headache).
- **Build output** goes to `backend/src/family_chores/static/` and is served by FastAPI. Dockerfile runs `npm ci && npm run build` in a multi-stage build, then copies the `dist/` contents into the final image.

---

## 8. Lovelace card (secondary UI)

- LitElement + TypeScript, single bundled `family-chores-card.js`.
- Reads **HA entities only** (not the add-on API). Subscribes to state changes for the points/streak sensors and the pending-approvals sensor.
- Config:
  ```yaml
  type: custom:family-chores-card
  members: [alice, bob]       # optional filter; default = all discovered
  show_pending_approvals: true
  tap_action:
    action: navigate
    navigation_path: /hassio/ingress/local_family_chores
  ```
- Does **not** try to complete chores directly — tapping a chore navigates to the Ingress app. This keeps the card simple and the state model clean.
- Ships an editor (`family-chores-card-editor`) for Lovelace UI config.

---

## 9. Add-on manifest (`config.yaml`) essentials

Include at minimum:

```yaml
name: Family Chores
version: "0.1.0"
slug: family_chores
description: Family chore tracking and rewards, with HA entity bridging.
arch: [amd64, aarch64, armv7]
init: false
ingress: true
ingress_port: 8099
panel_icon: mdi:broom
panel_title: Family Chores
hassio_api: true
hassio_role: default
homeassistant_api: true
auth_api: true
map:
  - type: share              # for avatar uploads exposed to HA if desired
    read_only: false
options:
  log_level: info
  week_starts_on: monday
  sound_default: false
schema:
  log_level: list(debug|info|warning|error)
  week_starts_on: list(monday|sunday)
  sound_default: bool
```

Expose any user-tunable runtime setting through options so the user never has to exec into the container.

---

## 10. Dev loop

- `scripts/dev_backend.sh` runs FastAPI on localhost with a fake Supervisor responder (a small `aiohttp` stub) so you can develop without a running HA. Seed data via a `--seed` flag.
- `scripts/dev_frontend.sh` runs Vite dev server with a proxy to the local backend.
- End-to-end in HA: build the image for your arch, drop the folder into `/addons/` on HA OS via Samba/SSH, refresh the add-on store, install, start. Document this in `INSTALL.md`.
- Provide a `docker-compose.yml` for local-only (non-HA) testing of the backend and frontend together.

---

## 11. Testing & quality bar

- **Backend**: pytest + httpx. Minimum coverage:
  - Recurrence engine: one test per rule type, plus DST spring-forward and fall-back, plus month-end clamping for `monthly_on_date`, plus week-boundary for `points_this_week` reset.
  - Midnight rollover: pending → missed, streak increments correctly on all-done days, does not break on zero-chore days, resets on a missed day.
  - Approval flow: `done_unapproved` awards 0 points until `approve`; `reject` reverts state cleanly.
  - HA bridge: mock Supervisor, verify correct endpoints called for sensor writes, todo item create/update/remove, and event firing. Verify reconcile removes orphan todos.
  - Auth: Ingress headers trusted, PIN flow issues correctly scoped JWT, mutating endpoints reject without it.
  - DB corruption recovery path.
- **Frontend**: Vitest for the Zustand stores and any non-trivial components. Skip browser E2E for v1.
- `ruff` + `mypy --strict` on backend. `eslint` + `tsc --noEmit` on frontend and card. All wired into `scripts/lint.sh`.
- **CI**: GitHub Actions workflow that runs lint + tests on PR, and on tag builds multi-arch images (using `docker/build-push-action` with QEMU) and attaches them to the release.

---

## 12. Security

- PIN stored as argon2 hash with per-install random salt. Never return the hash, never log the PIN.
- Parent JWT signed with a secret generated at first startup and stored in `/data`. Rotate on user action only.
- Trust Ingress headers only when the request path comes through Ingress; reject `X-Remote-User` on any direct (non-Ingress) request if exposed. In normal HA OS deployment Ingress is the only path in, but defense in depth.
- Supervisor token: read once at startup into memory, never write to disk, never include in responses.
- Input validation on every endpoint via Pydantic. SQLAlchemy parameterized queries only; no string-formatted SQL anywhere.
- Avatar uploads: limit to 2MB, accept only PNG/JPEG/WebP, re-encode via Pillow to strip metadata, store under `/data/avatars/<uuid>.<ext>`.
- README must document the threat model plainly: add-on runs inside HA's trust boundary; anyone who can reach HA can reach this; the parent PIN is UX, not security.

---

## 13. Process expectations

- **Start with `DECISIONS.md`.** Before any code, write your plan: file tree confirmation, data-flow diagram (ASCII is fine), list of open questions. Then proceed.
- Commit in logical chunks with conventional-commit messages. Every commit must be runnable.
- After completing each of these milestones, stop and summarize for the human: (1) add-on manifest + Dockerfile boots cleanly, (2) DB + models + Alembic, (3) recurrence + instance generation + scheduler, (4) API + auth, (5) HA bridge, (6) SPA skeleton, (7) SPA polish + card, (8) tests + CI. Don't marathon to the end.
- If anything in this prompt conflicts with an HA add-on best practice or a current API behavior, follow the best practice and note the deviation in `DECISIONS.md`. Do not invent APIs — if unsure an endpoint exists, check HA developer docs and cite the page.
- Placeholders (`icon.png`, chime audio) are fine for v1; note them in `README.md` under "Assets to replace."

Begin with `DECISIONS.md`.
