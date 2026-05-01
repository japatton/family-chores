# DECISIONS — Family Chores add-on

Living design notes. New entries go at the top of each section; significant changes get a dated entry in §10 Changelog.

---

## 0. Project snapshot

**What we're building:** a Home Assistant Add-on (single Docker container, Ingress-served FastAPI + React SPA) that tracks family chores, rewards, and streaks. SQLite is the source of truth; a one-way bridge mirrors a curated subset of state into HA entities so the data is usable from automations and Lovelace. An optional thin Lit card reads those entities for an at-a-glance dashboard widget.

**Primary target:** a wall-mounted 10" tablet (1280×800, touch-only, landscape). UI must also work on phone and desktop, but the tablet is the design anchor.

**Non-goals (v1):** reward catalogue, per-kid PIN, TTS, photo-proof, multi-household sync. See §7 for where each future hook plugs in.

---

## 1. File tree (see §5 for restructure notes)

**Current layout (post-milestone-8 restructure — see §5):** the repo root
is an **HA add-on repository**, and the add-on itself lives in
`family_chores/`. HA Supervisor requires this shape (`repository.yaml` +
subdir per add-on) to accept the repo URL.

```
/                                # the add-on *repository*
├── repository.yaml              # metadata — marks this as an HA repo
├── README.md, LICENSE, DECISIONS.md, PROMPT.md, INSTALL.md
├── .github/workflows/           # CI + release pipelines
├── scripts/                     # dev / lint / probe scripts
├── lovelace-card/               # separate Lit card (not in the image)
└── family_chores/               # THE ADD-ON (what Supervisor builds)
    ├── config.yaml              # add-on manifest
    ├── Dockerfile
    ├── build.yaml
    ├── run.sh
    ├── icon.png, logo.png
    ├── DOCS.md                  # shown on Documentation tab
    ├── CHANGELOG.md             # shown on Changelog link
    ├── backend/                 # FastAPI + SQLAlchemy + Alembic
    └── frontend/                # React SPA
```

**Prompt-tree deviations** (logged in full in §5):
- Collapsed the prompt's outer `family-chores/` wrapper: the repo root
  IS `ToDoChore`, not a nested directory.
- `config.yaml` and all build files live inside `family_chores/`
  (required by HA Supervisor; see §5 milestone-8 entry).
- Added `services/` beside `core/` for DB-orchestrating code.
- Added `ha_todo_entity_id` column + `timezone` option.

The illustrative prompt subtree below is kept for reference — actual
files within `family_chores/backend/` and `family_chores/frontend/`
match this structure:

```
ToDoChore/
├── config.yaml                   # HA add-on manifest
├── Dockerfile
├── build.yaml                    # multi-arch base image map
├── run.sh                        # entrypoint (no s6, single process)
├── icon.png, logo.png            # placeholders (replace before release)
├── README.md
├── CHANGELOG.md
├── DOCS.md                       # Add-on "Documentation" tab
├── INSTALL.md
├── DECISIONS.md                  # this file
├── PROMPT.md                     # verbatim copy of build prompt
├── docker-compose.yml            # local-only dev (non-HA)
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── src/family_chores/
│   │   ├── __main__.py           # uvicorn entrypoint
│   │   ├── app.py                # FastAPI factory
│   │   ├── config.py             # loads /data/options.json
│   │   ├── scheduler.py          # APScheduler jobs
│   │   ├── api/                  # routers: members, chores, instances,
│   │   │                         #   auth, admin, ws, health
│   │   ├── core/                 # pure domain logic
│   │   │   ├── recurrence.py
│   │   │   ├── instances.py
│   │   │   ├── streaks.py
│   │   │   ├── points.py
│   │   │   └── time.py           # tz helpers, week-anchor math
│   │   ├── db/
│   │   │   ├── base.py           # engine/session
│   │   │   ├── models.py
│   │   │   └── migrations/       # Alembic versions
│   │   ├── ha/
│   │   │   ├── client.py         # Supervisor HTTP client
│   │   │   ├── sync.py           # debounced mirror service
│   │   │   └── reconcile.py      # startup + periodic reconciler
│   │   └── static/               # built SPA is copied here at image build
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── public/manifest.webmanifest
│   └── src/
│       ├── main.tsx
│       ├── app/                  # routes, layout, providers
│       ├── views/                # Today, Member, Parent
│       ├── components/
│       ├── hooks/
│       ├── store/                # Zustand slices
│       ├── api/                  # TanStack Query client + fetch wrapper
│       ├── ws/                   # WebSocket client
│       └── assets/               # chime.ogg, icons
├── lovelace-card/
│   ├── package.json
│   ├── rollup.config.mjs
│   └── src/
│       ├── family-chores-card.ts
│       └── family-chores-card-editor.ts
├── scripts/
│   ├── dev_backend.sh
│   ├── dev_frontend.sh
│   ├── dev_supervisor_stub.py    # fake Supervisor for local dev
│   └── lint.sh
└── .github/workflows/
    ├── ci.yml                    # lint + tests on PR
    └── release.yml               # multi-arch image build on tag
```

---

## 2. Data flow (authoritative diagram)

SQLite is the only source of truth. HA entities are a one-way mirror. Business logic **never reads state from HA** to make decisions.

```
  ┌─────────────────────────┐  Ingress HTTP + WS  ┌──────────────────────┐
  │  Browser (SPA)          │◀────────────────────▶│ FastAPI (port 8099)  │
  │  parents + kids         │                      │ ─ routers            │
  └─────────────────────────┘                      │ ─ APScheduler        │
                                                   │ ─ ha/sync.py (async) │
                                                   │ ─ SQLite (SoT) ◀───── source of truth
                                                   └───────────┬──────────┘
                                                               │ REST, Bearer $SUPERVISOR_TOKEN
                                                               │ http://supervisor/core/api/...
                                                               ▼
                                                   ┌──────────────────────┐
                                                   │ HA Core (mirror)     │
                                                   │  sensor.*_points     │
                                                   │  sensor.*_streak     │
                                                   │  sensor.pending_     │
                                                   │    approvals         │
                                                   │  todo.family_chores_ │
                                                   │    <slug> (per mbr)  │
                                                   │  + events fired      │
                                                   └──────────┬───────────┘
                                                              │ read-only subscribe
                                                              ▼
                                                   ┌──────────────────────┐
                                                   │ Lovelace Lit card    │
                                                   │ (secondary UI)       │
                                                   └──────────────────────┘
```

**Rules:**
1. Every write to SQLite that changes observable state enqueues a sync task. The enqueue call is non-blocking and the API response does not wait for HA.
2. `ha/sync.py` debounces same-entity bursts (500 ms window) and coalesces them into a single state update. Prevents hammering HA during bulk operations.
3. Retry policy: exponential backoff (0.5 s, 1 s, 2 s, 4 s, 8 s), max 5 attempts, per-entity queue cap of 1000 events. On overflow, drop oldest and log at warning level.
4. Reconcile on startup + every 15 min: for each member, fetch their `todo.family_chores_<slug>` items, compare against active instances, create missing / update changed / remove orphans.
5. If HA is unreachable, the UI keeps working. A banner flag ("HA bridge disconnected") is raised and cleared automatically on reconnection.

---

## 3. Technology choices

### Backend
| Concern | Choice | Why |
|---|---|---|
| Web framework | FastAPI + uvicorn (single worker) | Async, Pydantic v2 native, small footprint |
| ORM | SQLAlchemy 2.x (async) | Stable, good Alembic integration |
| Migrations | Alembic | Standard, script-based, easy rollback |
| Scheduler | APScheduler (AsyncIOScheduler) | In-process; no broker; fine for single container |
| HTTP client (HA) | httpx (async) | Same semantics as FastAPI, typed |
| Auth hashing | argon2-cffi | Modern default, fine memory/cpu knobs |
| JWT | PyJWT | Small, well-scoped, HS256 is sufficient |
| Images | Pillow | Metadata strip + re-encode |
| Logging | structlog → JSON | Structured, filterable, no secrets in fmt |
| Typing | mypy --strict | Catches lots of HA-API drift early |
| Lint | ruff | Fast, replaces flake8+isort+black-ish |

### Frontend (SPA)
| Concern | Choice | Why |
|---|---|---|
| Framework | React 18 + TypeScript | Most familiar, best tablet support |
| Build | Vite | Fast, simple, output is static files |
| Styling | Tailwind CSS | Utility-first, no component library needed |
| State | Zustand | Minimal, no providers, good for kid-flow view |
| Data | TanStack Query | Stale-while-revalidate, good offline UX |
| Routing | React Router v6 | Standard, Ingress-compatible with relative base |
| Animations | canvas-confetti + framer-motion (small) | Only where needed |
| Sound | HTMLAudioElement + OGG chime | No library needed |

### Lovelace card
| Concern | Choice | Why |
|---|---|---|
| Framework | Lit 3 + TypeScript | HA card convention |
| Bundling | Rollup | Smallest output, single file |
| Data source | `hass` state subscription only | Never hits the add-on API — keeps it decoupled |

---

## 4. Key design decisions (the ones future-me will question)

1. **Single container, no s6-overlay.** Uvicorn runs in the foreground under `run.sh`; APScheduler runs inside the FastAPI process. Simpler, fewer moving parts; downside is one process = one failure domain, which we accept.

2. **SQLite with WAL mode.** `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON`. Single writer (this process) means no contention.

3. **Alembic from day 1**, even for the initial schema. Backup `/data/family_chores.db` → `.bak` before any `alembic upgrade`. First migration writes the full v1 schema.

4. **Instance generation strategy:** lazy-generate on read with a 14-day horizon, plus a midnight rollover job that pre-materializes tomorrow and marks yesterday's `pending`/`done_unapproved` as `missed`. Lazy + pre-materialization together avoid both cold-start gaps and unbounded future rows.

5. **Midnight rollover is user-tz-aware.** Scheduler reschedules itself on DST boundaries. Uses `zoneinfo` (stdlib). Source of tz: `GET /api/config` on HA at startup, cached and re-fetched hourly. Override via add-on option `timezone_override` for edge cases.

6. **Points awarded on `done` state transition, not on `done_unapproved`.** For members with `requires_approval=true`, zero points awarded until a parent calls `approve`. `activity_log` records both events.

7. **Streaks: `done_unapproved` does NOT count.** Literal reading of the spec ("100% of that member's assigned instances ended in `done` (approved)"). This means slow parents can cost a kid their streak — we flag this friction point in the README and leave a hook to optionally "count provisionally" if feedback demands it.

8. **Streak milestones fire on transition, not on every read.** We compare streak before/after the day's recomputation and fire HA events only on the exact day the threshold is crossed. No duplicate fires on restart.

9. **Week-anchor reset.** Every rollover checks whether the member's stored `week_anchor` is in a prior week under the configured `week_starts_on`. If so, reset `points_this_week = 0` and update `week_anchor`. This is idempotent.

10. **`member_stats` is a cache, always rebuildable.** A maintenance endpoint (`POST /api/admin/rebuild_stats`) recomputes from `chore_instance` rows. Useful after schema changes or if someone notices drift.

11. **Auth model:**
    - **Identity** comes from HA via Ingress headers (`X-Remote-User`, `X-Ingress-Path`). We trust them when a request arrives on the Ingress socket path.
    - **Role elevation to "parent"** requires a PIN. Successful PIN → 5-minute HS256 JWT, scope `role=parent`. Every mutating admin endpoint checks the JWT.
    - **Kid endpoints** (list today, complete, undo) accept Ingress auth alone.
    - **JWT signing secret** is generated at first startup and stored in `app_config`. Rotated only on explicit user action.

12. **Debounce/retry knobs are explicit:** 500 ms debounce, 5 retries with 2× backoff starting at 500 ms, 1000-event per-entity queue, drop-oldest on overflow.

13. **WebSocket carries change notifications only, not snapshots.** Events are `{"type": "instance_updated", "id": 42}` and the client refetches via TanStack Query. Simpler serialisation, smaller payloads, harder to get out of sync.

14. **Ingress-relative URLs everywhere.** The frontend fetches from `./api/...`, never absolute. Ingress path is variable per-install and per-user.

15. **No service worker.** PWA manifest yes (for "add to home screen"), but SW + Ingress is a known trap and not worth the complexity.

16. **Lovelace card never calls the add-on API.** Read-only via `hass` state. Tap → navigate to Ingress. This keeps the state model unambiguous (one mutating path only).

17. **No `custom_components/` integration, no config flow.** Pure add-on.

18. **Avatars:** accept PNG/JPEG/WebP up to 2 MB, re-encode via Pillow to strip EXIF and enforce max 512×512, store as `/data/avatars/<uuid>.<ext>`. Emoji avatars stored inline as string.

19. **Week start default:** Monday. Configurable via add-on option.

20. **Placeholder assets.** `icon.png`, `logo.png`, and the completion chime ship as placeholders. Listed in README "Assets to replace."

21. **DB datetimes are naive UTC.** SQLite has no real timezone support and SQLAlchemy's `DateTime(timezone=True)` on SQLite just strips the tz anyway. Storing naive datetimes that represent UTC keeps the contract unambiguous. `family_chores.core.time.utcnow` is the only canonical way to mint a "now" value for the DB; `to_local(dt, tz)` is the only canonical way to convert back for "today"-style logic.

22. **Enum columns stored as strings (`native_enum=False`).** Adding a new `InstanceState` or `RecurrenceType` becomes a pure code change — no ALTER TABLE, no data-migration for existing rows. The downside (losing SQL-side enum validation) is acceptable given we validate via Pydantic at the boundary anyway.

23. **Python-side defaults for `created_at`/`updated_at` (not `server_default`).** Keeps the convention identical across dialects and makes unit-testable. `onupdate=utcnow` at the ORM layer triggers on any UPDATE through SQLAlchemy — good enough since we're the only writer.

24. **PRAGMAs applied via `connect` event on `engine.sync_engine`.** `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=NORMAL`. This is the SQLAlchemy-canonical way to ensure the PRAGMAs are set for every pooled connection, including the ones Alembic opens.

25. **Alembic runs sync against the same SQLite file as the async runtime.** Simpler than the async-Alembic pattern; `env.py` creates its own sync engine and the PRAGMA event is reused. The runtime app never uses this sync path.

26. **Alembic config is constructed programmatically at runtime** (migrations live inside the installed package). `backend/alembic.ini` exists for dev CLI use only and is not shipped in the Docker image runtime path.

27. **`.bak` snapshots must checkpoint WAL first.** When WAL mode is active, most committed state lives in the `-wal` sidecar file until a checkpoint flushes it into the main DB. Copying only the main file yields a torn snapshot — we hit this during milestone 2 integration testing and the bug was silent: backups appeared to succeed but contained almost nothing. Fix is `PRAGMA wal_checkpoint(TRUNCATE)` before the copy. Sidecars are also scrubbed before a restore so a stale `-wal` can't overlay a freshly-restored main file.

28. **Full DB corruption must include sidecars to be detectable.** Corollary of #27: corrupting just the main file doesn't actually corrupt the database from SQLite's view, because WAL still has the real pages. The recovery tests explicitly nuke `-wal`/`-shm` to model disk loss or filesystem damage, which is what the recovery path is actually designed for.

29. **Streaks are computed as of yesterday, not today.** At midnight rollover we pass `streak_as_of = today - 1` to `compute_streak`. Otherwise the moment we generate today's PENDING instances (which we do *in the same rollover*), today has non-DONE states and the streak walk returns 0 on every rollover. This matches the prompt's wording ("100% of that member's assigned instances **ended** in `done`") — today hasn't ended yet. Caught while writing `test_rollover_fires_each_milestone_exactly_once`.

30. **Milestone events fire only on the exact transition**, not on re-crossings. `crossed_milestone(prev, new)` returns the threshold iff `prev < threshold <= new`. A streak that breaks and later re-crosses the same milestone does NOT refire — we treat that as acceptable friction for v1 to keep the event stream quiet and the bridge stateless. If families complain, we can add a "last-milestone-fired" column to `member_stats` and be smarter.

31. **Catch-up rollover runs on every app boot**, using the same `run_rollover` pipeline as the midnight cron. Every step (`mark_overdue`, stats recomputation, `generate_instances`) is idempotent, so this is safe — and it guarantees the DB is consistent from the very first request even if the add-on was down when midnight fired yesterday.

32. **APScheduler is optional at boot via env var.** `FAMILY_CHORES_SKIP_SCHEDULER=1` disables the scheduler startup in the lifespan. Used by `test_lifespan_integration.py` to avoid leaking APScheduler threads into pytest's event loop; the scheduler factory's behaviour is unit-tested separately.

33. **Effective timezone falls back to UTC until HA tz fetching lands (milestone 5).** Added an `Options.timezone_override` that maps to a new `timezone: str?` option in `config.yaml`. If unset (or invalid IANA name), we use UTC. Not ideal — midnight rollover fires at UTC midnight instead of the user's local midnight — but the app is fully functional.

34. **Parent JWT: 5-min absolute TTL + `/api/auth/refresh` endpoint.** The prompt asks for "5 minutes of inactivity" — we model that by issuing short absolute JWTs and letting the frontend call `/refresh` on user activity. Pure absolute-TTL would cut active sessions mid-action; pure inactivity would require either server-side session state or per-request JWT rotation. The refresh approach is stateless on the server and trivial on the frontend.

35. **Global error envelope with `X-Request-ID`.** Every HTTP response (including validation and 500 errors) carries a correlation ID in a header and in the body. Supplied IDs are honoured (`X-Request-ID: abc` round-trips), else we mint a 12-hex-char token. `DomainError` subclasses map cleanly to HTTP codes; Pydantic `RequestValidationError` output is passed through `jsonable_encoder` to strip the `ValueError` objects Pydantic v2 stashes in `ctx`.

36. **WebSocket protocol: change-notification only.** Events are `{"type": "instance_updated", "instance_id": 42, "member_id": 3, "state": "done"}` and the client is expected to refetch the affected resource. Two reasons: (a) halves the coupling between UI and DTO shapes (DTOs can evolve without breaking WS consumers), (b) dead-simple multi-client broadcast — every connected socket sees the same payload.

37. **Chore create/update triggers `generate_instances` inline.** Otherwise creating a chore at 3 pm means nothing shows up for today until the midnight rollover. `generate_instances` is already idempotent and cheap at family scale (≤100 new rows), so calling it on every chore mutation is essentially free.

38. **`MemberStats` fields must be explicitly initialised on construction.** `mapped_column(default=0)` only fires at INSERT time, not attribute access, so `stats.points_total + delta` on a fresh transient row raised `TypeError: NoneType + int`. `adjust_member_points` now builds stats rows with explicit zeros; the `recompute_stats_for_member` path happens to write every field from queries so it didn't hit this. Caught while writing milestone-4 service tests.

39. **HA bridge is a single async worker task with a wake event.** Routers/services call `bridge.notify_*`; those push onto in-memory sets / lists and set `_wake`. The worker sleeps on `_wake.wait()`, then sleeps an additional `debounce_seconds` before flushing, so a burst of notifications (e.g. one API request that mutates three things) coalesces into a single HA pass. One `_flush_lock` guarantees `force_flush` (used by tests and the reconciler) can't race with the timer. On any `HAUnavailableError` or unexpected exception the worker sleeps with exponential backoff (0.5 s → 60 s cap) and re-arms itself — a dropped event is re-queued before the re-raise.

40. **Bridge client is constructed from the environment, not injected into routers.** `make_client_from_env()` picks `SUPERVISOR_TOKEN` (add-on path) over `HA_URL`+`HA_TOKEN` (local dev). If neither is set, the lifespan installs a `NoOpBridge` so the app still runs fully — the UI never sees "HA is down" beyond the `ha_connected: false` flag in `/api/info`.

41. **Events fire AFTER state-change DB commit, from the bridge worker.** Routers enqueue the event payload during their synchronous mutation path; the worker fires them asynchronously. This keeps the HTTP response fast (we don't wait for HA) and ensures no event references a transaction that later rolled back.

42. **Todo item identity uses a stable summary prefix: `[FC#<instance_id>] <chore_name>`.** HA doesn't return UIDs from `todo.add_item`, so after every add we call `todo.get_items` once, find the freshly-added item by our FC tag, and write its UID back to `chore_instance.ha_todo_uid`. The tag also lets the reconciler distinguish "our" items from anything the user put on the list manually — those are left alone.

43. **Inline stats recompute in instance routers.** Every state transition (`complete`, `undo`, `approve`, `reject`, `skip`) calls `recompute_stats_for_member` before commit so the HTTP response's `/today` view shows the new totals. The alternative — letting the bridge recompute asynchronously — would leave the UI showing stale points for a beat after a tap, which feels broken on a kid tablet.

44. **Timezone resolution order: `timezone` option → cached HA `/api/config → time_zone` → UTC.** Lifespan tries an HA config fetch at startup (short timeout; best-effort) and caches the result on `app.state.effective_timezone`. Routers read via the `get_effective_timezone` dependency. Scheduler jobs were built with this tz in milestone 3 — from milestone 5 onward, the tz is typically the real local tz, and midnight rollover fires at local midnight as intended.

45. **Add-ons cannot create `todo.*` entities.** The prompt called for `todo.family_chores_<slug>` per member but add-ons aren't HA integrations and cannot register the `todo` platform. Users create one **Local To-do** per family member via HA's UI and paste the entity ID into the member record. `member.ha_todo_entity_id` is nullable: unset means "no todo sync for this member; sensors + events still publish." INSTALL.md §"HA To-do Setup" documents this.

46. **Startup reconcile blocks briefly; periodic reconcile catches anything the bridge dropped.** Lifespan awaits `reconcile_once` before accepting requests so a restart after HA downtime converges state before the first API call. The 15-min scheduled job is the safety net for mid-run bridge failures.

47. **Frontend uses `HashRouter`.** The add-on is served at a variable Ingress path (`/hassio/ingress/local_family_chores/`). Vite emits relative asset URLs (`base: './'`) so all CSS/JS loads correctly, and `HashRouter` sidesteps the basename-threading problem for in-app routes. URLs look like `/#/member/alice`, which is fine under an Ingress panel (users don't deep-link into an iframe).

48. **SPA build output is gitignored.** `backend/src/family_chores/static/*` is ignored except for `.gitkeep`. The Dockerfile has a dedicated `frontend-build` stage that runs `npm ci && npm run build` into `backend/src/family_chores/static/`; the final image `COPY --from=frontend-build` pulls it in. No minified JS noise in git diffs, and the final image always bakes a fresh SPA.

49. **FastAPI's static-mount gate keys on `index.html`, not "dir is non-empty".** The `.gitkeep` would falsely trip the old "dir has any file" check, so we'd mount `StaticFiles` and return 404 for `/`. Keying on `index.html` correctly falls through to the fallback HTML (with a "run `npm run build`" hint) when the SPA hasn't been built.

50. **Fluid typography via Tailwind custom font-size tokens (`fluid-xs`…`fluid-3xl`).** Each token is a `clamp()` formula on viewport width, so type scales smoothly between phone and 32" portrait without discrete breakpoints. Paired with `min-h-touch = 4.5rem` (72 px) on every interactive surface.

51. **Per-member theming via a single CSS variable.** Components set `style={{ '--accent': member.color }}`; `.themed` and `.themed-soft` utility classes use `color-mix()` to derive backgrounds. Zero runtime theme engine, no CSS-in-JS — a variable + gradient.

52. **TanStack Query is the only data-cache.** Zustand holds transient / localStorage-persisted bits (parent token + expiry, sound-enabled). Routers call `queryClient.invalidateQueries` from the WS event handler, so any mutation made in another tab (or by the HA bridge) re-syncs without a manual refresh.

53. **Parent token + sliding refresh on the client.** `useParentStore` keeps `{token, expiresAt, lastActivity}`; `isActive()` gates the gate. Client can call `/api/auth/refresh` on activity to renew — matches the spec's 5-min-inactivity semantic without server-side session state.

54. **Completion chime is Web Audio, not a binary asset.** `useChime` builds a short A5 → C#6 bell via `AudioContext` + `OscillatorNode` + `GainNode`. Two-line synthesis, zero binary payload, ships offline. Silent failure if the browser has suspended audio (first tap of the session may be silent; subsequent ones work because the tap counts as user activation).

55. **Confetti uses `canvas-confetti` imperatively.** The library injects its own canvas into `document.body`; wrapping it in React is more friction than value. `fireConfetti({ accent })` is called from the completion `onSuccess` callback. Palette is `[member.color, white, yellow]` — the tap feels personally theirs.

56. **Burn-in shift via a 90-second `background-position` animation.** On a 32" wall-mounted panel, static UI elements risk image retention. The body background is a 300% × 300% gradient animated over 90 s — unnoticeable to foveal attention, does its job in peripheral. Respects `prefers-reduced-motion`.

57. **Lovelace card ships as a separate build artefact.** Rollup bundles Lit + decorators into a single ES-module file (~26 KB minified) at `lovelace-card/dist/family-chores-card.js`. Loaded via HA's `/local/` + Resources registration, not via the add-on's HTTP API. The card only reads entities the bridge publishes — if something's wrong with the add-on, the card silently shows no rows, which is a useful diagnostic by itself.

58. **Card tap navigates to the Ingress app by default.** The prompt's suggested `tap_action.navigation_path` defaults to `/hassio/ingress/local_family_chores`. Not every install has that exact slug (users can rename), so the editor exposes an override; the card is happy with a bare config in the common case.

59. **Card editor is built into the same bundle** via a direct `import`. HA's custom-card picker calls `getConfigElement()` which returns a fresh `<family-chores-card-editor>`; since the editor module is registered at import time in the same bundle, no lazy-loading dance is needed.

60. **Two selective ruff ignores.** `RUF059` (unused unpacked variable) fires in every `for a, b in ...` where one side is documentation — common pattern in tests. `UP042` wants `StrEnum` everywhere we use `(str, Enum)`; identical behavior, no migration payoff. Everything else in `RUF` + `UP` stays on.

61. **Apscheduler silenced as untyped-imports.** Three per-line `# type: ignore[import-untyped]` comments in `scheduler.py`. A per-module `[[tool.mypy.overrides]]` block also adds `disable_error_code = ["import-untyped"]` for defence in depth.

62. **Frontend tests use happy-dom, not jsdom.** ~10× faster startup, which matters on a laptop and in CI. Only friction so far: fake timers + React 18 + userEvent interact badly; we skipped a tricky countdown test in `UndoToast` and instead test the render + click paths. The full tap-toast-undo flow is integration-tested via the running app.

63. **ESLint flat config on typescript-eslint v8.** One `eslint.config.js` handles SPA + type-ignores; the card's Rollup pipeline typechecks via `tsc --noEmit` (simpler, fewer moving parts for a ~200-line codebase).

64. **CI matrix splits backend / frontend / card.** Backend job runs `ruff` + `mypy --strict` + `pytest`. Frontend runs `eslint` + `tsc` + `vitest` + `vite build`, uploads the built SPA as a CI artefact. Card runs `tsc` + `rollup`, uploads the bundled JS. Keeps the individual job logs readable and lets cached-dep installs parallelise.

65. **Release workflow uses a three-stage fan-in.** One `build-image` job per arch (amd64/aarch64/armv7) pushes to GHCR via QEMU; one `build-card` job produces the bundle; a single `publish-release` job downloads the card artefact and creates a GitHub Release with release notes pointing at the GHCR tags and the card JS attached.

---

## 5. Deviations from prompt

- **2026-04-21 — dropped `map: [- type: share]` from `config.yaml`.** The prompt's sample manifest declared `share` access "for avatar uploads exposed to HA if desired." Avatars are served by our own FastAPI under `/api/avatars/...`, so there's no user-facing reason to make them visible at `/share`. Dropping this shrinks the add-on's permission surface. If a real need appears (e.g. using an avatar in HA notification attachments), re-add.
- **2026-04-21 — added `tini` as ENTRYPOINT.** The prompt said "no s6 needed for single process," which is true — tini isn't s6, it's a ~100KB init to reap zombies and forward signals so `docker stop` / add-on stop doesn't take 10 s to SIGKILL. Common pattern for single-process containers.
- **2026-04-21 — added `startup: application` and `boot: auto` to `config.yaml`.** Not mentioned in the prompt but standard for HA add-ons that depend on HA Core being up. `application` defers start until HA Core is ready, matching our reconcile-on-startup behaviour.
- **2026-04-21 — added `services/` directory alongside `core/`.** The prompt's file tree lists `core/` for "pure domain logic" but routes DB-backed orchestration (mark overdue, generate instances, recompute stats) through the scheduler. Putting async-session-using code under `services/` keeps `core/` genuinely pure (no SQLAlchemy imports) and makes unit tests easy. Prompt tree was illustrative; no conflict with §10.
- **2026-04-21 — added `timezone` option to `config.yaml`.** Not in the prompt's manifest snippet; needed so the scheduler has a sensible tz before milestone 5's HA tz fetching lands. Optional string (`str?`); empty = fall back to UTC.
- **2026-04-21 — replaced `todo.family_chores_<slug>` with user-managed Local To-do entities.** Rooted in the add-on-vs-integration constraint (see §4 #45). User-facing impact documented in INSTALL.md. Changes `member.ha_todo_entity_id` nullable string to the schema.
- **2026-04-21 — revised design target for the SPA.** Prompt §1 said "wall-mounted tablet, landscape, ~10" @ 1280×800." Actual target is a **32" portrait touchscreen @ 2160×3840**, still wall-mounted. Must also be usable on phones and other devices. Shift from "tablet-landscape-first" to **mobile-first responsive** with the large-portrait mode as the design anchor. 72 px min tap targets retained; no hover affordances (confirmed touch-only). Fluid type via `clamp()` so typography scales with viewport rather than jumping at breakpoints. Today view grid: 1 col (phone) → 2 col (tablet / 32" portrait). No impact on milestones 1–5 — backend is viewport-agnostic.
- **2026-04-22 — restructured into an HA add-on *repository* layout.** Initial push to GitHub had `config.yaml` at the repo root, which HA Supervisor rejects with "not a valid app repository." Supervisor expects `repository.yaml` at root + one subdirectory per add-on. Moved all add-on files (`config.yaml`, `Dockerfile`, `build.yaml`, `run.sh`, `icon.png`, `logo.png`, `DOCS.md`, `CHANGELOG.md`, `backend/`, `frontend/`, `.dockerignore`) under `family_chores/`. Added `repository.yaml` at root. `lovelace-card/` stays at root (separate artefact). Scripts and CI workflows updated with the new paths; three test files had `from backend.tests._ha_fakes` imports that relied on the pre-move layout — switched to `from tests._ha_fakes` which works via pytest's rootdir/sys.path handling. All 243 tests still pass after the move.

---

## 6. Security posture (summary; README has the user-facing version)

- Add-on sits inside HA's trust boundary. Anyone who can reach HA can reach this. Parent PIN is UX, not security.
- Supervisor token lives in memory, never written to disk, never included in responses.
- PIN is argon2-hashed with a per-install random salt.
- Every endpoint is Pydantic-validated.
- SQLAlchemy parameterized queries only.
- `X-Remote-User` is trusted only when the request arrives via the Ingress path. Non-Ingress requests that assert the header are rejected.
- Logs never contain PINs, JWTs, argon2 hashes, or the Supervisor token — enforce with a structlog processor that redacts by key name.

---

## 7. Future hook points (v2+)

These are explicitly out of scope for v1, but we leave the architecture unbent so they don't require rewrites.

- **Reward catalog.** Add `reward` + `reward_redemption` tables; `points_total` already tracks a spendable balance; a new router + parent view covers it. No bridge changes needed (or mirror redemptions as events).
- **Per-kid PIN.** Add `member.pin_hash` column; reuse the parent JWT flow with a different scope (`role=kid:<id>`). The `display_mode` field already hints at per-member surface differences.
- **Voice/TTS announcements.** Already fire HA events on completion/approval/milestone; user can wire those to `tts.*` services via standard automations. Hook point = event payload shape (keep it stable).
- **Photo proof.** Extend `chore_instance` with `proof_image_path`; reuse the avatar upload path. Bridge publishes a `has_proof` attribute on the instance's todo item if we want it.
- **Multi-household.** Non-trivial — would need a `household` scoping column on every table. Not architected for; would be a v2 major rewrite. Noted.

---

## 8. Open questions (original list + resolution status)

### Resolved by live probe against HA 2026.4.1 (2026-04-21)

1. **HA `todo` service semantics — RESOLVED.**
   - `todo.add_item` does **NOT** support `return_response=true` (returns 400
     "Service does not support responses"). No way to learn the created
     item's UID from the call itself.
   - `todo.get_items` *requires* `return_response=true` and returns each item
     with a server-assigned `uid`, `summary`, `status`, `due`, `description`.
     **This is the canonical read path.**
   - `todo.update_item` / `todo.remove_item` accept either the UID or the
     summary as the `item` field (UID wins on conflict).
   - **Items are NOT in the entity state's `attributes` in 2026.4.** The
     state is just the open-count; `items` is only surfaced through
     `todo.get_items` service calls. This is a behaviour change from
     earlier HA versions — we cannot use a single `GET /api/states/<entity>`
     call to learn items.
   - `due_date` works only on entities that expose `SET_DUE_DATE_ON_ITEM`
     (feature bit 16). `todo.shopping_list` does **not** support it and 500's
     if you pass `due_date`. **Local To-do** entities do support it.
   - Custom events: `POST /api/events/family_chores_probe` returned 200 with
     `{"message": "Event family_chores_probe fired."}`.
   - HA exposes its configured timezone at `GET /api/config → time_zone`
     (e.g. `"America/Chicago"`).

2. **`hassio_role: default` grant scope — NOT VERIFIED yet.** The probe
   used an LLAT, not an add-on context. `default` is documented as giving
   access to `/api/states`, `/api/services`, `/api/events`, `/api/config` —
   keep as-is and re-check once the add-on is actually installed in HA OS.

3. **Ingress header reliability — NOT VERIFIABLE outside of an installed
   add-on.** Keep the `"anonymous"` fallback in `deps.get_remote_user`. If
   real installs show the header missing intermittently, we'll add a
   stricter path later.

4. **Env vars — SETTLED.** Current HA OS exposes `SUPERVISOR_TOKEN`. The
   older `HASSIO_TOKEN` is gone in supported versions. Client reads
   `SUPERVISOR_TOKEN` first, falls back to explicit `HA_URL`/`HA_TOKEN`
   env vars for local development.

### Closed by earlier milestones

5. **Alembic at runtime — SETTLED.** Programmatic `Config`, migrations ship
   inside the package.
6. **DST + scheduler — ACCEPTED.** Date-only recurrence is unit-tested
   across spring-forward / fall-back. The APScheduler cron side only
   exercises in a live install.
7. **WebSocket through Ingress — NOT VERIFIABLE outside of an installed
   add-on.** Starlette/FastAPI WS works under TestClient; the add-on will
   verify on first real install.
8. **`share` map — DROPPED.** See §5.

### New open question from the probe

- **We can't *create* `todo.*` entities from an add-on.** Add-ons are not
  integrations. Users must provision one Local To-do per family member.
  We store each mapping in a new nullable `member.ha_todo_entity_id`
  column; if unset the bridge skips todo sync for that member but still
  publishes sensors + events. Instructions live in `INSTALL.md` §"HA
  Todo Setup".

---

## 9. Milestones (from prompt §13)

1. ☑ Add-on manifest + Dockerfile boots cleanly — commit `d058db9`
2. ☑ DB + models + Alembic — commit `9c2aea4`
3. ☑ Recurrence + instance generation + scheduler — commit `5d124dc`
4. ☑ API + auth — commit `863abde`
5. ☑ HA bridge — commit `f45d443`
6. ☑ SPA skeleton — commit `f95ccba`
7. ☑ SPA polish + Lovelace card — commit `e8fd483`
8. ☑ Tests + CI — this milestone

Stop and summarize for the human after each.

---

## 10. Changelog

- **2026-04-21** — Initial DECISIONS.md. File tree confirmed with one deviation (collapsed `family-chores/` wrapper since working dir is already `ToDoChore/`). All major tech choices recorded. Open questions queued against milestone 4. No code yet — next step is user sign-off on this plan, then milestone 1.
- **2026-04-21** — Milestone 1 complete (`d058db9`). Three manifest deviations logged in §5.
- **2026-04-21** — Milestone 2 complete. Added §4 entries #21–#28 covering DB conventions, PRAGMAs, Alembic integration, and the non-obvious WAL-backup pitfall we hit during integration testing. No new prompt deviations.
- **2026-04-21** — Milestone 3 complete. Added §4 entries #29–#33 (streak-as-of-yesterday, milestone transition semantics, catch-up rollover, scheduler skip flag, UTC fallback). Two new prompt-tree additions logged in §5 (`services/` dir, `timezone` option). Caught a real-world-feel bug while testing — today's PENDING instances breaking the streak on the same rollover that generated them — documented as #29.
- **2026-04-21** — Milestone 4 complete. Added §4 entries #34–#38 (parent JWT + refresh, error envelope with request IDs, WS notification-only protocol, inline instance generation on chore mutations, explicit MemberStats initialization). No new prompt deviations. 188 tests total (93 new): full HTTP coverage of every router, auth flow edge cases, WS hello/ping-pong/broadcast, global error shape, and service-level tests for undo-window expiry that need injected time.
- **2026-04-21** — Milestone 5 complete. Live probe against HA 2026.4.1 resolved §8 #1 and shaped the bridge design. Added §4 entries #39–#46 (async worker with debounce + backoff, env-based client discovery, deferred events, FC tag identity pattern, inline stats recompute, tz fallback chain, Local To-do provisioning flow, blocking startup reconcile). Two new §5 deviations (user-managed Local To-do entities, `ha_todo_entity_id` column). 218 tests total (30 new).
- **2026-04-21** — Milestone 6 complete. React 18 + Vite SPA, 245 KB bundle (76 KB gzipped). Added §4 entries #47–#53 covering routing, build output, static mount, typography, theming, state management, and parent-mode refresh. Multi-stage Dockerfile now bakes the SPA at image-build time. Dev scripts (dev_backend.sh, dev_frontend.sh, lint.sh) added. Backend tests unchanged at 218 (SPA has no backend impact; frontend unit tests land in milestone 7 or 8 per `DECISIONS.md`).
- **2026-04-21** — Milestone 7 complete. SPA polish (Web-Audio chime, member-accent confetti, celebratory all-done screen, burn-in shift, sound toggle) + Lovelace card (`lovelace-card/` workspace, Rollup+Lit, ~26 KB single-file ES module with a GUI editor). Added §4 entries #54–#59. SPA bundle grew 245 KB → 259 KB (+5 KB gzipped) — all confetti. 218 backend tests still pass; both TS surfaces typecheck clean.
- **2026-04-22** — Milestone 8 complete. Backend clean under `ruff check` + `mypy --strict`; fixed real type bugs (int-of-None in recurrence config validation, `object`-typed HA client, `create_engine` arg) and added proper type annotations to every route handler. Frontend gets Vitest + happy-dom + @testing-library + ESLint flat-config; 25 new unit tests on stores, API client, PinPad, UndoToast, ProgressRing. Added §4 entries #60–#65. `scripts/lint.sh` now mirrors CI. Two GitHub Actions workflows: `ci.yml` (backend + frontend + card) on every PR; `release.yml` on tag builds multi-arch add-on images for amd64/aarch64/armv7 via QEMU, builds the card, attaches everything to a GitHub Release. 243 total tests (218 backend + 25 frontend), all green.
- **2026-04-23** — Phase 2 monorepo refactor complete (13 steps, commits `1a4e324`..`105325b`). Repo restructured into shared packages (`packages/{core,db,api}`) and thin deployment-target apps (the add-on stays at `family_chores/` per HA Supervisor convention; new scaffolds at `apps/{saas-backend,web}`). Auth identity abstracted behind `AuthStrategy` Protocol with three concrete impls (Ingress / Placeholder / Fake). Every tenant-scoped table gained a nullable `household_id` column + index (migration `0003_add_household_id`); every service threads `household_id` via a new `scoped()` helper — multi-tenancy plumbing in place from routers down to queries, addon path stays byte-identical via `IngressAuthStrategy` returning `None`. Tooling: uv workspace (5 members) + pnpm workspace (4 members); per-package CI matrix with a new `integration-addon` job that builds + boots the Docker image and asserts `/api/health` 200 + `/api/info ha_connected=false`; addon Dockerfile rewritten for repo-root build context with deps-ordered `pip install` (core → db → api → addon) and `pnpm --filter --frozen-lockfile` for the SPA. Tests: **364 total** across all targets — **218 backend baseline preserved exactly**, plus 12 migration tests, 6 scoped-helper unit tests, 5 multi-tenant integration tests via `FakeAuthStrategy` + `dependency_overrides`, 12 saas smoke tests (10 parametrized 501-on-tenant-scoped routes), 80 architecture-test parametrized cases (dep-arrows + packages-clean), and 2 web placeholder tests. Two known multi-tenant follow-ups deferred to `TODO_POST_REFACTOR.md` — `AppConfig.key` and `Member.slug` need composite-PK / composite-UNIQUE migrations before any SaaS row with a non-NULL `household_id` lands. User-facing change: `family_chores/CHANGELOG.md` gains one paragraph directing existing users through a normal HA Supervisor update (uninstall/reinstall as fallback if the build hiccups; slug-preserves-data for `/data/family_chores.db`). Per-step outcome logs in §11 below — note that the commit hashes inside individual step entries are off-by-one because each step amended its own commit to fill in its self-reference, but the *canonical* hash mapping is the per-step list at the top of this entry: step 1 `1a4e324`, step 2 `ead92a6`, step 3 `581bebf`, step 4 `fc1969d`, step 5 `e524c15`, step 6 `d1accc3`, step 7 `b3c3d33`, step 8 `287697b`, step 9 `471eacb`, step 10 `9c2a283`, step 11 `d03ae0d`, step 12 `3a5f55e`, post-12 fix `105325b`.

---

## 11. Monorepo refactor

Tracking prompt: **`PROMPT_PHASE2.md`** (to be committed at start of step 1). The refactor is purely structural — no user-facing changes, no new features. Goal: split shared code (`packages/core`, `/db`, `/api`) from deployment targets (add-on at `family_chores/`, plus future `apps/saas-backend/` and `apps/web/`), with the auth path abstracted and every tenant-scoped table gaining a nullable `household_id` so multi-tenancy can be added later without another migration earthquake.

**Layout asymmetry — deliberate.** The prompt's target tree nested the add-on under `apps/addon/`. We're keeping the add-on at **`family_chores/`** at the repo root instead, and only `saas-backend/` and `web/` live under `apps/`. Reason: HA Supervisor scans add-on repos for `config.yaml` files, and while it technically recurses, every convention-based add-on repo places each add-on as a direct child of the repo root (one level deep). We don't want the first live probe of Supervisor's deep-recursion behavior to happen during a user reinstall. Cost of the asymmetry: slightly inconsistent mental model ("apps/ for non-HA targets only"). Benefit: zero risk to existing HA installs. Decision logged 2026-04-23 after reviewer guidance on the phase-2 plan.

### Sequencing plan (13 steps; commit + green CI after each)

**Pre-flight (this entry):**
- Write §11 with plan, risks, questions. **Pause for review.** ← YOU ARE HERE

**Step 1 — Scaffolds + workspace tooling.**
- Copy the Phase 2 prompt verbatim to `PROMPT_PHASE2.md` (do not overwrite `PROMPT.md`).
- Create `TODO_POST_REFACTOR.md` with a single stub heading.
- Root `pyproject.toml` with `[tool.uv.workspace]` declaring the workspace members that exist at step-1 time: `packages/core`, `packages/db`, `packages/api`, `apps/saas-backend`. (The add-on joins as a workspace member in step 6 when its pyproject moves to `family_chores/pyproject.toml`.)
- Root `pnpm-workspace.yaml` declaring only `apps/web` for now. `family_chores/frontend` and `lovelace-card` are NPM-based today and join pnpm as part of step 7. Rationale: step 1 stays narrow (scaffolds + tooling proof), and pnpm won't try to link directories that still ship `package-lock.json`.
- Root `package.json` with `scripts.build = "pnpm -r build"`.
- Empty `packages/{core,db,api}` and `apps/{saas-backend,web}` with placeholder `pyproject.toml` / `package.json`, `__init__.py`, and a single `test_smoke.py` per python package. **No `apps/addon/` directory** — the add-on's scaffold work happens in-place at `family_chores/` during step 6. No logic moves yet. `uv sync` and `pnpm install` must both succeed at root.
- CI unchanged in this step — old jobs still point at `family_chores/`. Goal is just to prove the workspaces are valid.

**Step 2 — Move `core/` → `packages/core/`.**
- Relocate the four files (`recurrence.py`, `instances.py` *→ does not exist as a file today; core instance logic lives in services/; flag if I mis-mapped*, `streaks.py`, `points.py`, `time.py`) and their tests.
- Package name flips `family_chores.core` → `family_chores_core`. One mechanical import-path sweep across callers.
- Tests: all `test_recurrence.py`, `test_streaks.py`, `test_points.py` pass after moving. Zero test edits beyond imports.

**Step 3 — Move `db/` → `packages/db/`.**
- Relocate `base.py`, `models.py`, `startup.py`, `migrations/` (including `env.py` and both existing revision files). **Revision IDs must not change** — filenames stay as `0001_*.py` and `0002_*.py`, the `down_revision` chain is preserved.
- Extract SQLite PRAGMA `connect`-event hooks into `packages/db/src/family_chores_db/pragmas.py` (no behavior change — decisions #24, #27 still hold).
- `alembic.ini` moves to `packages/db/alembic.ini`; programmatic runtime `Config` (§4 #26) updates its `script_location`.
- Package name `family_chores.db` → `family_chores_db`. Mechanical import sweep.
- Tests: `test_models.py`, `test_startup_recovery.py` pass unchanged except imports.

**Step 4 — Move api (routers, services, schemas, WS, errors) → `packages/api/`.**
- Relocate `api/{auth,members,chores,instances,admin,ws,errors,schemas,deps}.py`, plus `services/{instance_service,instance_actions,rollover_service,stats_service}.py`, plus `security.py`. **`api/events.py` gets split per Q4**: the `EventProtocol` + concrete event constructors stay in `packages/api/src/family_chores_api/events.py`; the bridge-side HTTP `POST /api/events/...` call moves to `family_chores_addon.ha.bridge` in step 6.
- **`security.py` refinement per Q3**: rewrite `sign()` / `verify()` to take an explicit `secret: str` parameter — no module-level constant read. Routers get the secret via DI (an `SecretProvider` callable injected through `create_app`). Add-on wiring reads `app_config` row; `PlaceholderAuthStrategy` in saas scaffold raises. Module docstring documents this contract explicitly.
- `app.py` becomes `packages/api/src/family_chores_api/app.py` and is refactored into a `create_app(*, auth_strategy, bridge, static_dir=None, skip_scheduler=False)` factory that takes injected deps. Keep IngressAuth implementation in place **as a concrete class inside `deps/auth.py` temporarily** — the abstraction happens in step 5.
- The addon's `app_factory.py` (living inside `family_chores/` per the asymmetry; exact path pending Q1) wraps `create_app` and supplies addon-specific wiring (Supervisor env client, scheduler start, static dir path).
- Package name `family_chores.api` / `family_chores.services` → `family_chores_api.routers` / `family_chores_api.services`.
- Tests: all `test_api_*.py`, `test_instance_service.py`, `test_instance_actions.py`, `test_rollover.py`, `test_lifespan_integration.py`, `test_api_ws.py`, `test_api_errors.py` pass unchanged except imports and the new factory-based `conftest.py` fixture.

**Step 5 — Extract the AuthStrategy abstraction.**
- In `packages/api/deps/auth.py`: define `Identity`, `ParentIdentity`, `AuthStrategy` Protocol (`identify`, `require_parent`).
- Move the Ingress-specific implementation (`X-Remote-User` trust + parent-PIN JWT check) to the addon package at `family_chores/src/family_chores_addon/auth.py` (flattened layout per Q8) as `IngressAuthStrategy`.
- Tenant injection: add `deps/tenant.py` providing `get_current_household_id(identity)` which for `IngressAuthStrategy` returns `None` (single-tenant add-on mode).
- Add a `PlaceholderAuthStrategy` in `apps/saas-backend/` that raises `HTTPException(501)` on everything except `/health`.
- Add a test guard: `tests/test_packages_are_clean.py` greps `packages/api/src/` and `packages/core/src/` for `"supervisor"`, `"X-Ingress"`, `"X-Remote-User"`, `"HA_TOKEN"`, `"SUPERVISOR_TOKEN"` — must all be zero hits. Fails the suite if the addon starts leaking into shared packages later.
- Add the **dependency-arrow architecture test** (Q4): `tests/test_dependency_arrows.py` walks every `.py` under `packages/` and fails on any `from family_chores_addon`, `from family_chores_saas`, `import family_chores_addon`, or `import family_chores_saas`. Protects the `apps → packages` arrow permanently.
- Add a `FakeAuthStrategy` test fixture that returns a fixed household_id; use it in the scoping tests introduced in step 9.

**Step 6 — Restructure the add-on in-place at `family_chores/` (flattened layout, per Q8).**
- Add-on root stays at `family_chores/`. `config.yaml`, `Dockerfile`, `build.yaml`, `run.sh`, `icon.png`, `logo.png`, `DOCS.md`, `CHANGELOG.md`, `.dockerignore` do not move.
- **Flatten the backend layout (Q8).** Move the Python sources `family_chores/backend/src/family_chores/*` → `family_chores/src/family_chores_addon/*`. The `family_chores/backend/` wrapper directory is deleted. `family_chores/pyproject.toml` is created at the add-on root (replacing `family_chores/backend/pyproject.toml`). `family_chores/tests/` replaces `family_chores/backend/tests/` as the addon's test root. Final shape matches `apps/saas-backend/{pyproject.toml, src/family_chores_saas/, tests/}` symmetrically.
- Contents of the renamed package after steps 2–5 have extracted everything that belongs in `packages/`: `ha/` (client, bridge, reconcile), `scheduler.py`, `config.py` (options.json reader), `__main__.py`, plus the new `app_factory.py` (wires `create_app` with `IngressAuthStrategy` + `HABridge` + addon static dir) and `auth.py` (IngressAuthStrategy, moved in step 5). `ha/bridge.py` stays one file (prompt's `sync.py` split is illustrative; decisions #39–#43 stay intact).
- Addon `pyproject.toml` at `family_chores/pyproject.toml` declares workspace deps on `family-chores-core`, `-db`, `-api` + addon-only deps (httpx, APScheduler, argon2-cffi, PyJWT). The workspace member path in the root `pyproject.toml` is `family_chores`.
- Tests migrate `family_chores/backend/tests/` → `family_chores/tests/`. Imports flip from `family_chores.*` to `family_chores_addon.*` / `family_chores_api.*` / etc. Tests that exercise the HA bridge, reconciler, scheduler, or lifespan are conceptually addon-tests and belong here.
- **CHANGELOG note (user-facing, option b phrasing per Q7).** Append a paragraph to `family_chores/CHANGELOG.md`: "This release is a large internal restructure of the add-on's source tree. The normal HA Supervisor update flow should work — just click Update. If you see build errors during the update, uninstall and reinstall the add-on as a fallback: your data at `/data/family_chores.db` is preserved because the add-on **slug remains `family_chores`**, which is what HA Supervisor keys persistence on."
- HA Supervisor impact: zero. `repository.yaml` at repo root is unchanged; the add-on is still discovered as a direct child of the repo root; slug is unchanged.

**Step 7 — Ingress SPA stays at `family_chores/frontend/`, workspace-enrolled.**
- SPA directory does not move. `family_chores/frontend/` keeps its `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/`, `public/`, `tailwind.config.*`, `postcss.config.*`, `eslint.config.js`, `vitest.config.*`.
- Convert to pnpm: delete `package-lock.json`, regenerate `pnpm-lock.yaml` via `pnpm install` at workspace root. Add `family_chores/frontend` to `pnpm-workspace.yaml`.
- Update `family_chores/Dockerfile` `frontend-build` stage paths: `npm ci && npm run build` → `pnpm install --frozen-lockfile && pnpm run build`. Built output copies to `family_chores/src/family_chores_addon/static/` (flattened per Q8; same index.html-gate convention, decisions #48–#49 preserved).
- Frontend 25 vitest tests pass unchanged.

**Step 8 — The household_id migration.**
- New Alembic revision `0003_add_household_id` (down_revision = `0002_...`).
- Adds nullable `household_id VARCHAR(36)` + index on every tenant-scoped table: `member`, `chore`, `chore_assignment`, `chore_instance`, `member_stats`, `activity_log`, `app_config`. (Verify this list against `db/models.py` before writing the migration.)
- No backfill; no NOT NULL; no data changes.
- SQLAlchemy model columns added in parallel (`Mapped[str | None]`, default `None`).
- Up/down tests in `packages/db/tests/test_migration_0003.py` verify: old DB upgrades cleanly, new column is NULL on existing rows, downgrade drops the column without data loss.

**Step 9 — `scoped()` helper + per-service plumbing.**
- `packages/db/src/family_chores_db/scoped.py`: `def scoped(col, value): return col.is_(None) if value is None else col == value`. Exported for use by services.
- Every query in `packages/api/services/` that reads from a tenant-scoped table grows an optional `household_id: str | None = None` parameter and applies `scoped()`.
- Every router calls services with `household_id=Depends(get_current_household_id)`, which for `IngressAuthStrategy` returns `None` — so add-on behavior is unchanged byte-for-byte.
- New tests using `FakeAuthStrategy(household_id="abc")` verify that requests see only `"abc"`-scoped rows; the default addon path is also covered by every existing 218 tests staying green.

**Step 10 — `apps/saas-backend/` scaffold.**
- `pyproject.toml` declaring `family-chores-core`, `family-chores-db`, `family-chores-api` as workspace deps.
- `src/family_chores_saas/app_factory.py`: calls `create_app(auth_strategy=PlaceholderAuthStrategy(), bridge=NoOpBridge(), static_dir=None)`.
- `tests/test_smoke.py`: `/health` returns 200; every tenant-scoped endpoint returns 501.
- README.md with "Placeholder. Implementation in Phase 3."

**Step 11 — `apps/web/` scaffold.**
- `package.json` declaring the app as a pnpm workspace member. Vite + React + TS, bare-bones.
- `src/main.tsx` renders a single "Coming soon" placeholder.
- `tests/` with one vitest that asserts the placeholder renders.
- README.md with "Placeholder. Implementation in Phase 3."

**Step 12 — CI restructure.**
- Replace `ci.yml` with a matrix of parallel jobs as described in the prompt §8: `lint-python`, `test-core`, `test-db`, `test-api`, `test-addon`, `test-saas`, `lint-frontend`, `test-frontend`, `build-addon-frontend`, `build-card`, `build-addon-image`, `integration-addon` (new).
- `integration-addon`: boots the add-on image against `scripts/dev_supervisor_stub.py`, hits `/api/info`, asserts `ha_connected` flag + a couple of endpoints return 200.
- `release.yml` updates paths only (multi-arch build still runs, QEMU unchanged, card bundle job unchanged).
- Success criterion: wall-clock CI time on PRs ≤ today's.

**Step 13 — Close out §11.**
- Log every deviation encountered during steps 1–12 with commit hashes (§10-changelog style).
- Append any TODOs caught during the refactor to `TODO_POST_REFACTOR.md`.
- Final test count: 243 existing + ~20 new = **~263 total** (218 backend split across core/db/api/addon + 25 frontend + new scoping/migration/smoke tests). If it's materially higher, scope crept.

### What I expect to find tricky

1. **HA Supervisor add-on discovery path.** ✅ **Resolved 2026-04-23 before step 1:** add-on stays at `family_chores/` (direct child of repo root) instead of nesting under `apps/addon/`. Eliminates the risk of Supervisor's deep-recursion behavior being first exercised on live installs. Layout asymmetry documented above.

2. **Alembic revision chain survival.** The migrations live inside the Python package today (§4 #26) and are discovered via a programmatically-built `Config` in app startup. Moving them to `packages/db/` means updating the `script_location` in that programmatic config AND updating `packages/db/alembic.ini` for dev CLI use. Any test that expects the migrations to run from `backend/src/...` needs path surgery. Worth a dedicated commit.

3. **`api/services/` coupling to the HA bridge.** Current `instance_actions.py` and `rollover_service.py` import from `family_chores.ha.bridge` directly (via `notify_*` helpers) to enqueue HA updates. Per the "zero HA deps in packages" rule, the services need to call a `BridgeProtocol` passed through DI, and the concrete `HABridge` lives with the addon package (`family_chores_addon.ha.bridge`). Need to trace every `from ...ha...` import in services to confirm the interface surface before step 4. If it's more than 3–4 methods, I'll hold a spot in step 4 for a small `BridgeProtocol` definition in `packages/api/deps/bridge.py`.

4. **Static-dir injection into `create_app`.** Today `app.py` mounts `StaticFiles` from a path it computes relative to the package directory (§4 #48 #49). In the refactor the static SPA lives in the addon package, which `packages/api/` can't know about. Plan: `create_app(..., static_dir: Path | None = None)` mounts iff provided, preserving the `index.html`-gate. Addon passes `Path(__file__).parent / "static"`.

5. **Dockerfile build context.** `family_chores/Dockerfile` currently uses `family_chores/` as its build context, but it now needs the repo root (to install workspace-member packages from `packages/`). GHA's `docker/build-push-action@v5` accepts a `context:` key — will set it to `.` (repo root) and a `file:` of `family_chores/Dockerfile`. `family_chores/.dockerignore` stays in place but must no longer exclude `packages/`. A new root-level `.dockerignore` may also be needed to keep the build context lean.

6. **pnpm migration of the existing SPA.** Mostly mechanical (`pnpm import` consumes `package-lock.json` and emits `pnpm-lock.yaml` preserving resolutions), but peer-dep warnings may surface differently. Budget one round of "silence peer warnings" triage.

7. **Tests that relied on rootdir/sys.path tricks.** §5 (2026-04-22 restructure) noted three test files fixed by switching from `from backend.tests._ha_fakes` to `from tests._ha_fakes`. With tests now split across four pytest roots (`packages/core/tests`, `packages/db/tests`, `packages/api/tests`, `family_chores/tests`), a shared `_ha_fakes.py` needs a new home — likely a `tests/_fixtures/` shared package or a `conftest.py` at repo root that registers the fixture directory. Will decide in step 4 when the api tests move.

8. **Test count arithmetic.** The prompt asks for "all 243 existing tests still pass unchanged." Some existing tests inherently cross the new package boundaries (e.g. `test_lifespan_integration.py` exercises app startup, DB, HA bridge, scheduler all at once). These stay at `family_chores/tests/` because that's where the wiring lives, even though the DB code under test is in `packages/db/`. Integration-style tests belong to the composition root. Will call this out explicitly in step 4 commits.

### Clarifying questions — all resolved 2026-04-23

1. **HA Supervisor add-on discovery.** ✅ **Resolved.** Add-on stays at `family_chores/` at repo root. See "Layout asymmetry" paragraph above.

2. **`db/startup.py` home.** ✅ **Resolved.** Goes to `packages/db/src/family_chores_db/recovery.py`. Apps call it from their own lifespan.

3. **`security.py` (argon2 + JWT).** ✅ **Resolved with refinement.** Lives at `packages/api/src/family_chores_api/security.py`. **Signing-secret injection:** expose `sign(payload, secret)` / `verify(token, secret)` — no module-level secret constant. Each app sources its own secret (add-on reads from `app_config` row; future SaaS reads from env / secret manager). Module docstring documents this explicitly so no future contributor re-introduces a default.

4. **`api/events.py` split.** ✅ **Resolved with refinement.** Split in two:
   - `packages/api/src/family_chores_api/events.py` defines an **`EventProtocol`** (shape: `event_type: str`, `payload: dict`) and concrete event constructors (`MilestoneCrossed`, `ChoreCompleted`, etc.) that implement it. Routers build events against the protocol.
   - The addon's `family_chores_addon.ha.bridge` consumes events via the `EventProtocol` and makes the actual HTTP `POST /api/events/...` call.
   - **Architecture test (new):** `tests/test_dependency_arrows.py` at repo root walks every `.py` file under `packages/` and fails if any of them contain `from family_chores_addon`, `from family_chores_saas`, or `import family_chores_addon` / `import family_chores_saas`. This keeps the arrow pointing apps → packages only, permanently.

5. **`scoped()` helper home.** ✅ **Resolved.** `packages/db/src/family_chores_db/scoped.py`.

6. **pnpm migration.** ✅ **Resolved with guardrail.** Migrate to pnpm. If pnpm's strict resolution surfaces undeclared transitive deps during step 1 or step 7, **fix the `package.json` properly** — no `shamefully-hoist-true`, no `public-hoist-pattern=*` escape hatch. Declare every actually-used dep as a direct dep.

7. **User-facing CHANGELOG guidance.** ✅ **Resolved with softer phrasing (option b).** The CHANGELOG paragraph describes a normal HA Supervisor update flow as the default path; uninstall-and-reinstall is named as a *fallback* if the user sees build errors, not the default instruction. Slug-preserves-data note stays.

8. **`backend/` wrapper keep or flatten.** ✅ **Resolved — flatten.** Use `family_chores/src/family_chores_addon/` with `family_chores/pyproject.toml` at the add-on root. No `backend/` wrapper. Rationale: establishes the same `pyproject.toml + src/<pkg>/` shape that `apps/saas-backend/` and future deployment targets will use, making the repo structurally legible across all Python deployment roots. `frontend/` stays as-is because it's genuinely a different kind of thing (pnpm/TypeScript project, not a Python src-layout package).

### Alignment with existing decisions §1–§10

No direct conflicts found. Specifically:

- **§4 #26** (programmatic Alembic config) survives — only the `script_location` path changes.
- **§4 #29–#33** (rollover / streaks / timezone) are pure-core logic that moves to `packages/core/` unchanged.
- **§4 #34–#38** (auth / errors / WS) become API-package concerns; the `AuthStrategy` abstraction is a refinement, not a reversal.
- **§4 #39–#46** (HA bridge) stay inside the add-on at `family_chores/`, just under a renamed package (`family_chores.ha.*` → `family_chores_addon.ha.*`). The `BridgeProtocol` interface in `packages/api/` is new but doesn't contradict any prior decision.
- **§4 #45** (user-provisioned Local To-do entities via `ha_todo_entity_id`) stays verbatim. The column's home (now `packages/db/`) doesn't change its semantics.
- **§4 #48–#49** (SPA static mount + `index.html` gate) survive — the static dir just moves with the addon.
- **§7 "multi-household"** was flagged as "v2 major rewrite." This refactor pays down that cost by adding the `household_id` column and scoping plumbing now, so the eventual switch-on is a migration that flips NOT NULL + a new auth strategy, not a rewrite.

### Step outcomes (running log)

- **Step 1 — 2026-04-23, commit `1a4e324`.** Workspace tooling scaffolded. Two unanticipated bits surfaced and were resolved inline:
  - The pre-existing `.venv/` was stale and uv didn't editable-install the new workspace members into it; `rm -rf .venv && uv sync --all-packages` recreated it cleanly.
  - Pytest's default `prepend` import mode collided across the four packages' `tests/test_smoke.py` modules (same module name, different files). Fixed by setting `addopts = ["--import-mode=importlib"]` at the root `pyproject.toml`.
  - Decided uv's virtual workspace pattern (`tool.uv.package = false` at the root) so the root `[project]` block can stay a stub.
  - Test count after step 1: 4 stub smoke tests + the existing 218 backend + 25 frontend (untouched).

- **Step 2 — 2026-04-23, commit `ead92a6`.** Pure domain logic moved to `packages/core`. **One in-scope architectural fix:** `core.recurrence` and `core.streaks` previously imported `RecurrenceType` / `InstanceState` from `family_chores.db.models`, which (combined with `db.models` importing `core.time.utcnow`) was a package-level circular reference that the new "core has no DB deps" rule forbids. Extracted those two enums to **`family_chores_core.enums`**; `db/models.py` imports them from core and re-exports them under its own namespace so existing addon callsites doing `from family_chores.db.models import RecurrenceType` keep working without a sweep. `DisplayMode` stays in `db.models` — it's a UI preference, not domain logic. Surprises and resolutions:
  - The workspace `.venv` couldn't run the addon's tests until `family_chores/backend` was enrolled as a temporary uv workspace member (it'll move to `family_chores` in step 6 when the `backend/` wrapper is flattened per Q8). Logged in the root `pyproject.toml` comment.
  - Aggregate root-level `pytest` runs failed with `'async_generator' has no attribute add_all` until `asyncio_mode = "auto"` was added to the root `[tool.pytest.ini_options]` — pytest only honors the first ini-file walked up from the rootdir, so the addon's own pytest config was being ignored on aggregate runs. Per-package CI runs (which `cd` into a member first) were unaffected.
  - The addon's `pyproject.toml` gained one workspace dep declaration (`family-chores-core`) plus an explanatory comment; the addon source itself wasn't touched beyond the mechanical import sweep.
  - Test count after step 2: **218 backend tests still pass**, redistributed as 57 in `packages/core/tests/` (test_recurrence + test_streaks + test_points) + 161 in `family_chores/backend/tests/` + 3 remaining stub smokes (db/api/saas) = 221 Python tests collected at the root. Frontend 25 tests untouched.
  - Zero `TODO_POST_REFACTOR.md` additions — every drift candidate I noticed (e.g. the pre-existing FastAPI `asyncio.iscoroutinefunction` deprecation warnings on Python 3.14) was either truly out-of-scope or pre-existing and explicitly not a step-2 concern.

- **Step 3 — 2026-04-23, commit `7bdfeb4`.** Data layer moved to `packages/db`. Relocated `models.py`, `base.py`, `startup.py → recovery.py` (Q2 rename), both Alembic migration revisions (`0001_initial`, `0002_member_ha_todo` — revision IDs preserved unchanged), `env.py`, and `alembic.ini`. Extracted the SQLite PRAGMA connect-event hook from `base.py` into `packages/db/src/family_chores_db/pragmas.py` and promoted its leading underscore off (`_install_sqlite_pragmas` → `install_sqlite_pragmas`) — the helper's now a public surface of the db package. Outcomes and surprises:
  - **`packages/db/pyproject.toml` grew its first real dep block** (sqlalchemy[asyncio]/aiosqlite/alembic + `family-chores-core` workspace dep) plus a `[tool.setuptools.package-data] family_chores_db = ["migrations/**/*"]` glob — without that, non-editable wheel installs would lose the migration scripts and `default_alembic_upgrade` would 404.
  - **Alembic `script_location` updated** in both places: `packages/db/alembic.ini` (dev CLI; points at `src/family_chores_db/migrations`) and implicitly via `Path(__file__).parent / "migrations"` inside `recovery.default_alembic_upgrade` (runtime). The runtime path auto-corrected because it's derived from `__file__` — no code change needed, just the file move.
  - **`family_chores.db.startup` → `family_chores_db.recovery`** rename affected exactly one addon callsite (`app.py`'s `from ...startup import BootstrapResult, bootstrap_db`). Swept cleanly.
  - **~20-file sed sweep** turned every `from family_chores.db.X` into `from family_chores_db.X`. The `_install_sqlite_pragmas` rename required a separate conftest edit because that one import combined base + pragmas on a single line (`from family_chores.db.base import Base, _install_sqlite_pragmas`); split into two imports.
  - **No dependency-arrow violations introduced.** `packages/core/` and `packages/db/` both grep-clean for any `family_chores.*` (addon) imports — verified before commit. Arrow is now `addon → db → core`.
  - **Migration revision IDs preserved** (`0001_initial`, `0002_member_ha_todo`). The migration *filenames* are unchanged too; git detected them as renames. End-to-end Alembic still works — `test_lifespan_integration.py` (which runs `bootstrap_db` → `default_alembic_upgrade` → real migrations) is part of the 142 passing addon tests.
  - **Test distribution after step 3:** packages/core = 57, packages/db = 19 (test_models + test_startup_recovery), family_chores/backend = 142. Total = **218 backend tests still pass** (unchanged). Aggregate root run including stub smokes for api + saas = 220 Python tests collected. Frontend 25 untouched.
  - **Zero `TODO_POST_REFACTOR.md` additions.** One candidate noted but *not* added: `family_chores/backend/tests/conftest.py` still has a `sys.path.insert(0, _SRC)` hack that predates the uv workspace install and is now redundant; removing it is a trivial post-refactor cleanup, but it isn't broken so I left it alone rather than scope-crept.

- **Step 4 — 2026-04-23, commit `a7388a6`.** API layer relocated to `packages/api`. Moved 5 routers (auth, members, chores, instances, admin), the `ws` route, services (4 files), schemas, errors, deps, the WSManager, and `security.py`. Created `packages/api/src/family_chores_api/app.py` as a deployment-target-agnostic `create_app(*, title, version, lifespan, ...)` factory; rewrote `family_chores/backend/src/family_chores/app.py` as a thin wrapper that owns the lifespan, `/api/info`, and the SPA static mount. `BridgeProtocol` moved to `packages/api/src/family_chores_api/bridge.py` (concrete `HABridge` + `NoOpBridge` stay in the addon's `ha/bridge.py` for now; they import the protocol back). Outcomes:
  - **Options leak found and fixed.** Four routers (chores, admin, instances) and `deps.py` itself imported `family_chores.config.Options` — an addon class — to read `opts.week_starts_on` (and zero other fields). Surgical refactor: dead `opts` parameter deleted from `chores.py`'s two endpoints (declared but never used); `admin.py` + `instances.py`'s 6 sites switched to a new `get_week_starts_on(request) -> str` dep that reads `app.state.week_starts_on` (set by addon lifespan); `deps.py`'s `get_options` and the Options import deleted; `get_effective_timezone` falls back to `"UTC"` instead of `opts.effective_timezone`. Result: `packages/api/src/` grep-clean of every `from family_chores.*` (addon) import.
  - **Q3 secret-injection contract documented in `security.py`'s module docstring.** No code change needed — `mint_parent_token(secret, ...)` and `decode_parent_token(secret, ...)` already took the secret as an explicit parameter. The docstring now spells out who supplies it (addon mints + caches via `ensure_jwt_secret`/`app.state.jwt_secret`; future SaaS will read from env/secret manager).
  - **Q4 dependency-arrow architecture test added** at `tests/test_dependency_arrows.py`. Parametrized over every `.py` in `packages/` (42 files at this commit); fails with a precise per-file message if any line introduces a `from family_chores.X` / `from family_chores_addon` / `from family_chores_saas` import. Allows the workspace packages (`family_chores_core`, `_db`, `_api`) and is silent on addon test files (which are allowed to import addon code freely — they ARE the addon).
  - **`api/events.py` Q4 split was a misread.** That file is `WSManager` + WebSocket-event-type constants — not HA-event payload builders. The actual HA-event Q4 concern was already satisfied by the existing `BridgeProtocol.enqueue_event(event_type, payload)` method, which moved with the protocol to `packages/api`. No `Event` dataclass introduced (would force every call site to change for zero architectural benefit). Documented inline in `bridge.py`.
  - **Test redistribution unchanged in this step.** All API + service + integration tests stay at `family_chores/backend/tests/` because they exercise the full lifespan via `create_app(options=...)` from the addon's `conftest.py`, which still works (the addon's `app.py` re-exports a `create_app(options)` wrapper around the new factory). Moving them into `packages/api/tests/` would require a separate test-app-factory + fake auth-strategy fixture, which is step 5's natural home.
  - **Test count:** 57 (core) + 19 (db) + 0 (api — smoke removed) + 142 (addon) + 1 (saas-stub) + **42 (new dep-arrow parametrized cases)** = **261 Python tests**, all green. Backend baseline (218) preserved exactly. Frontend 25 untouched.
  - **TODO_POST_REFACTOR additions:** none. The `family_chores/backend/tests/conftest.py` `sys.path.insert` hack stays flagged-but-deferred from step 3.

- **Step 5 — 2026-04-23, commit `c329b7f`.** AuthStrategy abstraction extracted. Split `packages/api/src/family_chores_api/deps.py` into a `deps/` subfolder with 5 modules (`auth`, `db`, `bridge`, `runtime`, `tenant`); historic `from family_chores_api.deps import (...)` lines keep working via `__init__.py` re-exports. Defined `AuthStrategy` Protocol + `Identity` + `ParentIdentity` dataclasses; refactored every backward-compat shim (`get_remote_user`, `maybe_parent`, `require_parent`, `require_role`) to delegate through `app.state.auth_strategy` so a `PlaceholderAuthStrategy` actually returns 501 through the existing routers (instead of routers reading the Ingress header directly behind the abstraction's back). Created concrete `IngressAuthStrategy` (in the addon) and `PlaceholderAuthStrategy` (in the saas scaffold). Added `FakeAuthStrategy` test fixture in `packages/api/tests/conftest.py` for step 9's scoping tests. Outcomes:
  - **Tenant plumbing in place.** `Identity.household_id` carried through every request; `deps/tenant.py::get_current_household_id` returns it. The actual service-layer scoping lands in step 9.
  - **`extract_bearer` promoted off its leading underscore** in `family_chores_api.security` — both the in-package shims and the addon's `IngressAuthStrategy` parse the same Authorization header, so the helper is a public surface now (with module docstring noting why).
  - **Q3 contract holds.** `IngressAuthStrategy.__init__(secret_provider: Callable[[], str])` reads the JWT secret lazily from `app.state.jwt_secret` on every request, so a future secret-rotation endpoint can flip it in-place without re-constructing the strategy. No module-level secret constant anywhere.
  - **`tests/test_packages_clean.py` added** — parametrized HA-string-leak guard. Walks `packages/{api,core}/src` (excludes `db/src/` because `models.py` legitimately stores `ha_todo_entity_id` as a column name) and fails if any file contains `supervisor`, `X-Ingress`, `X-Remote-User`, `HA_TOKEN`, or `SUPERVISOR_TOKEN`. The test caught two real leaks in my own freshly-written docstrings (`deps/auth.py` and `deps/bridge.py`); paraphrased them out without hand-waving the architectural rule.
  - **Pytest collision: `tests/__init__.py` × multiple-conftest combo.** Adding `packages/api/tests/conftest.py` (alongside the addon's existing `family_chores/backend/tests/conftest.py`) triggered "Plugin already registered under a different name" on aggregate runs. Cause: `--import-mode=importlib` + per-package `tests/__init__.py` files made pytest discover the same conftest under multiple module paths. Fix: removed the empty `__init__.py` from `packages/{core,db,api}/tests/` and `apps/saas-backend/tests/` (importlib mode doesn't need them); kept it on `family_chores/backend/tests/` because three test files there import from `tests._ha_fakes` which requires the package marker.
  - **Test count:** 295 (= 218 backend baseline + 1 saas-stub + 76 architecture-test parametrized cases). Backend split unchanged from step 4 (57 core + 19 db + 142 addon); `packages/api/tests/` has the new conftest with `FakeAuthStrategy` but zero test files yet (those land in step 9). Architecture-test growth: dep-arrow 42→48 cases (the new `deps/` subfolder added 6 files); packages-clean adds 28 cases.
  - **TODO_POST_REFACTOR additions:** none. The `family_chores/backend/tests/conftest.py` `sys.path.insert` hack stays flagged from steps 3–4 (still functional, removing it is a future cleanup, not blocking).

- **Step 6 — 2026-04-23, commit `034f837`.** Add-on flattened in place at `family_chores/`. The `backend/` wrapper directory is gone; Python source now lives at `family_chores/src/family_chores_addon/` (Q8 layout), pyproject moved up to `family_chores/pyproject.toml`, tests moved up to `family_chores/tests/`. Python package renamed `family_chores` → `family_chores_addon`; project name (PyPI-normalised) renamed `family-chores` → `family-chores-addon` to match the workspace's hyphenated convention. HA Supervisor sees zero change — the add-on subdirectory is still `family_chores/`, slug is still `family_chores`, repository.yaml is unchanged. Outcomes:
  - **Two near-misses caught by the test suite.** First, `git mv backend/tests family_chores/tests` after `mkdir -p family_chores/tests` produced a nested `family_chores/tests/tests/` instead of moving contents (git's `mv` semantics: existing-dir destination = move-into rather than rename-to). Caught immediately by the post-sweep grep showing `tests/tests/_ha_fakes.py` paths. Fixed by re-moving each file up one level + `rmdir` the empty inner directory.
  - **Second:** the sed sweep was anchored to `^from` (line start), which missed three **inline** `from family_chores.X import Y` statements buried inside test function bodies (test_ha_bridge.py, test_ha_integration.py, test_ha_reconcile.py). Caught by the test run (3 ModuleNotFoundError failures); a follow-up sed without the `^` anchor cleaned them up. Lesson: any future rename sweep should drop the line-start anchor and add the dot/word-boundary on the right side instead.
  - **CHANGELOG note added** (option-b phrasing per Q7) under `[Unreleased] / Changed`. Tells users the normal HA Supervisor update flow should work; uninstall-and-reinstall is the fallback if they see build errors. Slug-preserves-data note included.
  - **Dockerfile fully rewritten** to drop every `backend/` reference. Build context paths now key off `pyproject.toml` / `src/` / `run.sh` directly. Frontend SPA build target updated in `vite.config.ts`: `../backend/src/family_chores/static` → `../src/family_chores_addon/static`. `.dockerignore` `backend/tests` → `tests`. Root `.gitignore` SPA-output path updated. `run.sh` entrypoint flipped: `python -m family_chores` → `python -m family_chores_addon`.
  - **The `_ha_fakes.py` cross-test import pattern still works** — `family_chores/tests/__init__.py` was kept intact for that reason (the rest of the workspace removed test `__init__.py`s in step 5). Three test files import `from tests._ha_fakes import FakeHAClient`; all pass.
  - **The conftest's `sys.path.insert(0, _SRC)` hack still works coincidentally** — `_SRC = Path(__file__).resolve().parents[1] / "src"` after the move resolves to `family_chores/src/` which is exactly where `family_chores_addon/` lives. Still redundant (uv editable-installs the addon as a workspace member), still flagged-but-deferred.
  - **Test count: 295** (= 218 backend baseline + 1 saas-stub + 76 architecture-test cases). Unchanged from step 5. `family_chores/tests/` continues to host all 142 addon tests.
  - **TODO_POST_REFACTOR additions:** none.

- **Step 7 — 2026-04-23, commit `5129afb`.** Frontend + Lovelace card migrated from npm to pnpm. Both `family_chores/frontend` and `lovelace-card` joined `pnpm-workspace.yaml` (now 4 workspace projects: root + apps/web + frontend + card); both `package-lock.json`s deleted; root `pnpm-lock.yaml` regenerated to cover all three frontend packages (317 packages, ~6 s install). Outcomes:
  - **Q6 guardrail held — no `shamefully-hoist=true`.** pnpm's strict-default resolution surfaced no undeclared transitive deps that needed escape hatches; both packages already declared every actually-used dep in their `package.json` (kudos to milestone-8 hygiene).
  - **Frontend vitest count is 26, not 25.** Confirmed: 6 files, 26 tests, 1.12 s. The "25" figure that's been carried in DECISIONS since step 1 was a stale snapshot from the milestone-8 commit; one test was added between then and now. Updating the running figure in this entry.
  - **Lovelace-card builds clean** under `pnpm --filter family-chores-card build` (rollup produced `dist/family-chores-card.js` in 674 ms — same artefact as before).
  - **Dockerfile frontend-build stage updated** with pnpm commands (`corepack enable && corepack prepare pnpm@9.15.0 --activate`, then `pnpm install --ignore-workspace --no-frozen-lockfile`, then `pnpm run build`). The `--ignore-workspace --no-frozen-lockfile` is a **deliberate, documented workaround**: HA Supervisor builds the addon with `family_chores/` as the Docker context, so the workspace `pnpm-lock.yaml` (sitting at the repo root) isn't reachable from inside the build. The frontend stage isn't pinned to the workspace lockfile right now; step 12 will revisit the addon image to make the Docker build fully reproducible across the workspace (and also fix the Python install stage, which has been broken since step 6 because `pip install /app` can't find the `family-chores-{core,db,api}` workspace deps on PyPI).
  - **Python test suite unchanged at 295.** Frontend changes don't touch any Python code; the dep-arrow + packages-clean tests still pass on every shared-package file.
  - **TODO_POST_REFACTOR additions:** none. The Docker-context limitation is logged in this DECISIONS entry + as a comment in the Dockerfile itself; step 12 owns the fix.

- **Step 8 — 2026-04-23, commit `4edb4ce`.** New Alembic migration `0003_add_household_id` (down_revision `0002_member_ha_todo`) adds a nullable `household_id VARCHAR(36)` column + index to all 7 tenant-scoped tables (`members`, `chores`, `chore_assignments`, `chore_instances`, `member_stats`, `activity_log`, `app_config`). Mirror columns added to every model class as `Mapped[str | None] = mapped_column(String(36))`. Outcomes:
  - **Migration is deliberately a no-op for existing data.** No backfill, no NOT NULL constraint. Existing rows get NULL, which the (yet-to-be-written, step 9) `scoped()` service-layer helper interprets as "no household filter" — query results stay byte-identical to pre-migration behavior. A future migration (after the SaaS is real and every row has a real household) will flip the column to NOT NULL.
  - **Index goes on every table even though only the SaaS-side query plan needs it.** The add-on's queries pass `None` and rely on `scoped(col, None) → col.is_(None)` which doesn't benefit from the index. Costs a few KB of B-tree per table; cheap insurance for the SaaS path.
  - **`ChoreAssignment` got a `household_id` of its own** even though it's a junction table — avoids a join-through-chore-or-member when the SaaS scopes assignment lookups.
  - **No `index=True` on the model columns.** SQLAlchemy's auto-naming for `index=True` is `ix_<column>` per-table, which would collide as 7 tables each tried to declare an index named `ix_household_id`. The migration explicitly creates `ix_<table>_household_id`; conftest's `Base.metadata.create_all` skips it (tests don't depend on the index for correctness).
  - **`packages/db/tests/test_migration_0003.py` is the first test in the suite that actually invokes Alembic** — every other test uses `Base.metadata.create_all` for speed. 12 cases: 5 functional (upgrade adds column, upgrade adds index, existing rows are NULL, downgrade is non-destructive, upgrade-down-up is idempotent) + 7 parametrized one-per-table (varchar(36) + nullable + not-PK).
  - **Test count: 309** (= 218 backend baseline + **12 new migration tests** + 1 saas-stub + 78 architecture-test cases). Architecture grew by 1 (dep-arrow walks the new migration file). Backend split unchanged at 57 core + 19 db (original) + 142 addon. The 12 migration tests live in `packages/db/tests/` — same package as the migration code.
  - **TODO_POST_REFACTOR additions:** none.

- **Step 9 — 2026-04-23, commit `1a950a8`.** Tenant-scope plumbing wired end-to-end. `family_chores_db.scoped(col, value)` helper added; threaded `household_id: str | None` through every service function (4 files, ~12 callsites) and every router endpoint that touches a tenant-scoped table (5 files, ~25 callsites including helper functions). Every read uses `scoped(Model.household_id, household_id)`; every insert sets `household_id=household_id`. Add-on path passes `None` (via `IngressAuthStrategy`) and the helper degenerates to `IS NULL`, so the 218 baseline tests stay byte-identical. Outcomes:
  - **42 query sites scoped** across the codebase. Bulk: 22 `select()` + 14 `session.get()` (all rewritten to scoped selects since `session.get` can't take WHERE clauses) + 6 `session.add()`.
  - **`security.py`'s `AppConfig` helpers also scoped.** `ensure_jwt_secret`, `get_pin_hash`, `set_pin_hash`, `clear_pin_hash` all take `household_id` and route through a new `_get_app_config(session, key, household_id)` shim that does a scoped select instead of `session.get`.
  - **Two known multi-tenant follow-ups logged in `TODO_POST_REFACTOR.md`** rather than fixed in step 9: `AppConfig.key` is still a single-column PK (two households can't both have a `jwt_secret` row), and `Member.slug` has a global UNIQUE (two households can't both have an `alice`). Both become blockers the day a SaaS writes a non-NULL-household row, but the addon doesn't care today (everything is NULL). Step 9's integration test works around the slug constraint by using distinct slugs per household.
  - **`packages/db/tests/test_scoped.py`** — 6 unit tests for the helper. Includes a regression-catcher that compiles `scoped(col, None)` to SQL and asserts `IS NULL` is in the output (would fail if someone "fixes" the helper to use `==` everywhere — the §4 trap from the migration prompt).
  - **`family_chores/tests/test_household_scoping.py`** — 5 integration tests that boot the full addon app, then swap `app.dependency_overrides[get_auth_strategy]` mid-test to a `FakeAuthStrategy(household_id="house-a")` / `("house-b")` to exercise multi-tenant isolation against a single shared DB. The same `TestClient` shifts between households across phases of one test. Tests prove: (a) house-a's member is invisible to house-b, (b) each household has its own member namespace, (c) dropping the override (back to addon's `IngressAuthStrategy`) only sees NULL-household rows — the `house-a` row is invisible to addon mode, (d) activity log scoped per household, (e) created member rows persist `household_id` to the DB.
  - **FakeAuthStrategy duplicated inline in `family_chores/tests/test_household_scoping.py`** — the same dataclass exists in `packages/api/tests/conftest.py` from step 5, but pytest's `--import-mode=importlib` doesn't share fixtures across test packages and importing the class itself would need sys.path gymnastics. The class is tiny (~20 lines); duplication costs less than the indirection. Logged inline in the file's docstring.
  - **Addon-side queries left unscoped** (`scheduler.py`, `ha/bridge.py`, `ha/reconcile.py`). They run in single-tenant addon mode where every row is NULL-household, so unscoped queries are equivalent to `WHERE household_id IS NULL`. If the same DB ever serves both addon-mode and SaaS-mode (which isn't a supported deployment), the bridge/reconciler would see other tenants' rows — a non-issue today, flagged in scheduler/bridge comments if future tracking matters.
  - **Test count: 322** (= 218 backend baseline + **6 scoped-helper unit tests + 5 multi-tenant integration tests** + 12 migration tests from step 8 + 1 saas-stub + 80 architecture-test cases (+2 from new packages files: scoped.py + test goals — the dep-arrow + packages-clean tests both walk the new files)). Backend baseline preserved. Frontend 26 untouched.

- **Step 10 — 2026-04-23, commit `2ec77e3`.** SaaS-backend scaffold composed end-to-end. `apps/saas-backend/src/family_chores_saas/app_factory.py` builds a real FastAPI app via `family_chores_api.create_app(...)` with a lifespan that installs `PlaceholderAuthStrategy` + an inline `_NoOpBridge` + the bare minimum `app.state` slots so dep resolution doesn't AttributeError. `apps/saas-backend/pyproject.toml` declares the three workspace packages as deps; `__init__.py` lazy-exports `create_app`. Outcomes:
  - **`/api/health` returns 200** — it's the only route that doesn't depend on auth/db deps, exactly as `family_chores_api.create_app`'s contract intends.
  - **Every tenant-scoped endpoint returns 501** — verified by a parametrized smoke test covering 10 route+verb combinations across members/chores/instances/today/admin/auth.
  - **First attempt blew up with `RuntimeError`** because the `session_factory` stub raised a non-HTTP error when `Depends(get_session)` resolved before `Depends(get_current_household_id)`. FastAPI evaluates a route's deps roughly in parallel; there's no guarantee the auth strategy wins the race. Fix: `_raise_501` stub raises `HTTPException(501)` directly so the response is 501 regardless of which dep bubbles first. Lesson logged inline in the factory's docstring — same pattern will apply to the future Postgres session factory's not-yet-wired error path.
  - **`_NoOpBridge` defined inline in the SaaS scaffold** rather than imported from `family_chores_addon.ha.bridge` — apps shouldn't import other apps. ~10-line class. Comment notes this could move to `packages/api/bridge.py` if a third deployment target ever needs the same no-op (premature for two consumers).
  - **Test count: 333** (= 322 from step 9 + **11 new saas tests**: 1 `__version__` smoke + 1 `/api/health` 200 + 10 parametrized 501 cases on tenant-scoped routes — but the existing 1-test smoke was replaced, so net delta is +11 - 1 = +10... let me recount: actually 322 + 11 = 333 because the parametrized one expanded the file's collection from 1 to 12). The factory-composability assurance is the real value: a future router or dep that implicitly assumes the addon's `IngressAuthStrategy` will fail one of these tests on the saas side before reaching prod.
  - **TODO_POST_REFACTOR additions:** none (the AppConfig-PK and Member.slug-uniqueness items from step 9 still apply; nothing new surfaced).

- **Step 11 — 2026-04-23, commit `8ee93e4`.** `apps/web/` filled in with a real Vite + React + TypeScript scaffold. New files: `package.json` (with proper deps + scripts), `vite.config.ts` (React plugin + vitest config keyed off happy-dom), `tsconfig.json` (mirrors the addon frontend's strict-mode settings), `index.html`, `src/main.tsx`, `src/App.tsx` (renders the "Coming soon" placeholder + a link to the GitHub repo), `tests/App.test.tsx` (2 vitest assertions: heading renders, repository link is present). Outcomes:
  - **`pnpm install` was a no-op at the lockfile level** ("Already up to date — resolved 363, reused 317") because every dep `apps/web` declares (`react`, `react-dom`, `vitest`, `happy-dom`, `@vitejs/plugin-react`, `@testing-library/react`, etc.) is already resolved in the workspace via `family_chores/frontend`. pnpm shared its global store; no extra disk hit.
  - **`pnpm --filter family-chores-web build` produces a 143 KB JS bundle (46 KB gzipped)** in 315 ms across 30 transformed modules. The addon frontend's bundle is comparable, so the toolchain is consistent.
  - **2/2 vitest tests pass** in 561 ms. Kept tests minimal — heading + link presence — since `App.tsx` is a deliberate placeholder.
  - **No Tailwind, no router, no TanStack Query.** Step 11 is *scaffold*, not *Phase 3 web app*. The addon frontend's `package.json` declares ~15 deps for the kid-tablet UX; the web placeholder gets by with `react` + `react-dom` + the test/build toolchain. Adding more would invite scope creep and lock in choices that should wait for the real Phase-3 design.
  - **Workspace test suite total: 28 frontend** (26 addon + 2 web). Python tests unchanged at 333.
  - **TODO_POST_REFACTOR additions:** none.

- **Step 12 — 2026-04-23, commit `d9a61f8`.** CI restructured into a parallel matrix and the long-deferred Docker fixup landed.
  - **Dockerfile rewritten for repo-root build context.** Frontend stage uses pnpm (`corepack` + `pnpm@9.15.0`) with `--filter family-chores-frontend --frozen-lockfile` against the workspace lockfile — drops step 7's `--ignore-workspace --no-frozen-lockfile` workaround; fully reproducible. Python stage installs the four workspace packages **in dependency order** (`core → db → api → addon`) via plain `pip install /local/path` — pip treats local paths as wheels-for-resolution and finds each `family-chores-*` dep already-installed when resolving the next package. No uv in the runtime image (keeps it lean), no PyPI hit for workspace deps. Step-6's broken state ("`pip install /app` can't find family-chores-core on PyPI") is fixed.
  - **Root `.dockerignore` added** covering `.git`, `.venv`, `__pycache__`, `node_modules` (any depth), built SPA dirs, tests, and docs. Keeps the repo-root build context lean.
  - **Local `docker build` not verified** — Docker isn't installed on this dev machine. The new `integration-addon` CI job is the validation point; if the Dockerfile is broken it'll fail there before merge.
  - **`ci.yml` replaced with a parallel matrix:**
    - `python` matrix over [core, db, api, addon, saas] — pytest per package.
    - `python-arch` runs the workspace-root architecture tests (dep-arrows + packages-clean).
    - `python-lint` runs `ruff check` workspace-wide + `mypy --strict` on the addon.
    - `frontend` matrix over [addon-frontend, web, lovelace-card] — conditional lint/typecheck/test/build per package + artefact upload.
    - `build-addon-image` — amd64 Buildx + GHA cache, image tarball uploaded.
    - `integration-addon` (NEW) — `docker load` + container boot, polls `/api/health` for up to 30 s, then asserts `/api/info` reports `ha_connected=false`. No Supervisor stub needed: addon's `make_client_from_env` returns None without `SUPERVISOR_TOKEN` and the lifespan installs `NoOpBridge` cleanly.
  - **`release.yml` updated** to repo-root context + pnpm install for the Lovelace card. Multi-arch QEMU+Buildx unchanged.
  - **`scripts/lint.sh` rewritten** for the monorepo (uv per-package + pnpm for frontends). Clear "uv not found" / "pnpm not found" errors instead of the old hand-rolled .venv check.
  - **PEP 561 `py.typed` markers added** to `packages/{core,db,api}/src/family_chores_*/`. Addon's `mypy --strict` was bombing on every line that subclassed `BridgeProtocol` or used the `@app.get` decorator from a workspace import (mypy treated cross-package imports as `Any`). The marker tells mypy "this package ships type info" and the spurious errors disappear. `package-data` globs updated so `py.typed` ships with the wheel.
  - **`packages/api/tests/test_fake_auth_strategy.py` added** — `pytest` exits 5 ("no tests collected") on an empty directory, which trips `set -e` in `scripts/lint.sh`. Two small async tests cover the fixture's `identify` + `require_parent` paths via the `fake_auth_strategy` conftest fixture.
  - **Auto-fixed 13 ruff `I001` import-order findings** that the pre-step-12 lint script never ran across the moved locations. All in addon test/source files left over from steps 4–9's import sweeps.
  - **Test count: 336** (= 333 from step 11 + 3 new: 2 in `test_fake_auth_strategy.py` + 1 net-new arch-test case from the new `py.typed` files). Backend baseline (218) preserved. Frontend 28 untouched. `scripts/lint.sh` exits 0 end-to-end.
  - **TODO_POST_REFACTOR additions:** none. The "addon image needs an `image:` field in `config.yaml` so HA Supervisor pulls from GHCR instead of building locally" topic is mentioned in the Dockerfile header but not added to the post-refactor list — it's a deployment-config decision the owner makes once the GHCR namespace is settled.

- **Step 13 — 2026-04-23, post-fix `105325b`.** Phase 2 close-out. **No new code in this entry** — it's the canonical "everything's done, here's the inventory" record. Outcomes:
  - **§10 changelog** gained the canonical Phase-2 dated entry with the per-step commit-hash mapping (above the per-step entries below). That entry — not this one — is what future-me should read first when reviewing the refactor.
  - **Per-step hash drift acknowledged.** Each step entry above has a `commit <hash>` reference that is **one rev behind** the actual commit (because the entry was added in a `--amend` cycle that itself changed the hash). The §10 entry's per-step list is the authoritative mapping. Considered fixing the per-step entries individually but the chain is endless: amending step-N to fix step-N's hash bumps step-N's hash again. Left as-is, with this caveat documented here.
  - **`TODO_POST_REFACTOR.md` swept.** Two items remain (both surfaced in step 9):
    - `AppConfig.key` single-column PK can't host multi-tenant rows with the same key — needs composite-PK migration before SaaS lands.
    - `Member.slug` global UNIQUE can't host two households' `alice`s — needs composite-UNIQUE migration.
    - Plus one pre-existing cleanup carry-over: `family_chores/tests/conftest.py`'s `sys.path.insert(0, _SRC)` hack is now redundant under uv editable installs but functional; leaving for a separate trivial-cleanup PR.
  - **Final test inventory:**
    | Location | Count |
    |---|---|
    | `packages/core/tests/` | 57 |
    | `packages/db/tests/` | 37 (19 model/recovery + 12 migration + 6 scoped-helper) |
    | `packages/api/tests/` | 2 (FakeAuthStrategy fixture smoke) |
    | `family_chores/tests/` | 147 (142 addon + 5 multi-tenant integration) |
    | `apps/saas-backend/tests/` | 12 (1 import + 1 health + 10 parametrized 501) |
    | `tests/` (architecture) | 81 (49 dep-arrows + 32 packages-clean) |
    | **Python total** | **336** |
    | `family_chores/frontend` (vitest) | 26 |
    | `apps/web` (vitest) | 2 |
    | `lovelace-card` | typecheck only |
    | **Frontend total** | **28** |
    | **Aggregate** | **364** |
  - **218 backend baseline preserved exactly.** Every test that existed at the start of step 2 still passes; the +118 net-new Python tests are the architecture / migration / scoping / saas-smoke layers added during the refactor.
  - **Docker validated locally** (post-step-12, `105325b`): `docker build -f family_chores/Dockerfile -t family-chores:local .` from repo root produces a 613 MB / 148 MB-content arm64 image; the container boots, lifespan runs, `/api/health` returns 200 and `/api/info` reports `ha_connected=false` + `bootstrap.action=initialized`. The string-literal `family_chores.app:create_app` reference in `__main__.py` (a step-6 sweep miss) was caught and fixed in the same session — the kind of bug the new `integration-addon` CI job is designed to catch.
  - **Deviations from the original §11 plan**, full list:
    1. Add-on stayed at `family_chores/` instead of moving to `apps/addon/` (Q1, decided pre-step-1, layout-asymmetry note).
    2. Add-on Python source flattened to `family_chores/src/family_chores_addon/` (no `backend/` wrapper) — Q8, decided pre-step-1.
    3. `RecurrenceType` + `InstanceState` enums extracted to `family_chores_core.enums` to avoid a circular dep (step 2 surprise, not in the original plan).
    4. `ChoreAssignment` got its own `household_id` (step 8 — junction tables also scoped to avoid join-through-FK).
    5. `AppConfig.key` PK + `Member.slug` UNIQUE deliberately NOT migrated to composite — deferred to TODO_POST_REFACTOR (step 9).
    6. PEP 561 `py.typed` markers added to `packages/{core,db,api}` (step 12 — needed for `mypy --strict` to see workspace types).
    7. `FakeAuthStrategy` duplicated inline in `family_chores/tests/test_household_scoping.py` rather than imported from `packages/api/tests/conftest.py` (pytest's `--import-mode=importlib` doesn't share fixtures across test packages).
    8. `addon` `image:` field NOT added to `config.yaml` (deferred deployment-config decision; documented in Dockerfile header).
  - **Phase 2 is closed.** Future SaaS work (Phase 3) starts from the SaaS scaffold + the two TODO_POST_REFACTOR follow-ups, with the architecture tests as the safety net to catch any future drift.

---

## 12. Public release polish

Tracking prompt: post-v0.2.1 release-polish prompt (received 2026-04-24, after the v0.2.1 tag was already published and GHCR images live). Goal is repository-level governance + documentation for a stranger landing from a Reddit link or search result, *without disturbing what shipped*. Branch: `release-polish` off `main` at `63be636`.

### Pre-work inventory (2026-04-24)

**Critical divergence from the prompt's stated context up front:** the prompt §0 says `family_chores/README.md` exists. **It does not.** There is only a repo-root `README.md`. This invalidates §4.2 (which assumes a VERIFY action and forbids touching that file) and changes the §4.1 install-section plan (which links to `family_chores/README.md`). Recommendation deferred to "Open questions" below.

#### Path-by-path inventory

| Path | State | Lines/notes | Prompt §  | Recommended action |
|---|---|---|---|---|
| `/README.md` | EXISTS | 165 lines; has Title, Why, How it works, **Screenshots** (added 2026-04-24, commit `63be636`), Install→`INSTALL.md`, Threat model, Features (v1), Roadmap, Assets to replace, Development, License (says MIT) | §4.1 | EDIT (significant divergences from §4.1 spec — see "Open questions" Q1) |
| `/LICENSE` | **MISSING** | — | §4.8 | CREATE MIT (matches README claim) and flag for human confirm |
| `/CONTRIBUTING.md` | MISSING | — | §4.9 | CREATE |
| `/SECURITY.md` | MISSING | — | §4.10 | CREATE with `YOUR_CONTACT_EMAIL_HERE` placeholder |
| `/CODE_OF_CONDUCT.md` | MISSING | — | §4.11 | CREATE (Contributor Covenant 2.1) with `YOUR_CONTACT_EMAIL_HERE` |
| `/.github/ISSUE_TEMPLATE/` | MISSING | (only `.github/workflows/` exists today) | §4.12 | CREATE dir + `bug_report.yml` + `feature_request.yml` + `config.yml` |
| `/.github/PULL_REQUEST_TEMPLATE.md` | MISSING | — | §4.13 | CREATE |
| `/docs/` | EXISTS | 1 entry (`screenshots/`) | §4.14/§4.15 | EXTEND (add `architecture.md` + `roadmap.md`) |
| `/docs/screenshots/` | EXISTS | 7 PNGs (see image inventory below) | — | LEAVE; reference at current paths |
| `/docs/architecture.md` | MISSING | — | §4.14 | CREATE |
| `/docs/roadmap.md` | MISSING | — | §4.15 | CREATE |
| `/family_chores/README.md` | **MISSING** | (prompt says exists; it does not) | §4.2 | **OPEN QUESTION Q1** — see below |
| `/family_chores/DOCS.md` | EXISTS | 83 lines; has First-run setup, Configuration, Entities published, Lovelace card section, Events fired, Troubleshooting (3 FAQs), Support | §4.3 | EDIT (gaps vs spec: missing Dashboard integration, Backup and restore, Privacy; troubleshooting wants 4–6 FAQs has 3) |
| `/family_chores/CHANGELOG.md` | EXISTS | 180 lines; v0.2.1 + v0.2.0 entries plus full milestone-N history | §4.4 | VERIFY only — entries byte-identical guarantee |
| `/family_chores/icon.png` | EXISTS | 570 bytes — confirmed placeholder | §6 | LEAVE; existing README's "Assets to replace" already flags |
| `/family_chores/logo.png` | EXISTS | 888 bytes — confirmed placeholder | §6 | LEAVE; same as above |
| `/family_chores/translations/en.yaml` | MISSING | (translations dir doesn't exist) | inventory only | LEAVE; not in CREATE/EDIT scope per §4 |
| `/lovelace-card/README.md` | EXISTS | 82 lines; tagline, install (Manual + HACS-not-yet-supported placeholder), Configuration, "Why a separate card". Reasonably complete. | §4.5 | EDIT (update HACS section since HACS is now planned via this prompt; add screenshot reference; tighten relationship-to-addon) |
| `/lovelace-card/hacs.json` | MISSING | — | §4.6 | CREATE |
| `/lovelace-card/info.md` | MISSING | — | §4.7 | CREATE (under 30 lines; HACS pre-install view) |
| `/lovelace-card/CHANGELOG.md` | MISSING | — | §4.7 | CREATE (Keep-a-Changelog seeded with `[Unreleased]` + `[0.1.0]`) |
| `/lovelace-card/package.json` | EXISTS | version `"0.1.0"` | §4.6 verify | NO CHANGE; lovelace-card CHANGELOG seeds from this version |
| `/RELEASE_NOTES_v0.2.1.md` | MISSING | — | §4.16 | SKIP per spec (no retroactive release notes) |
| `/TODO_POST_REFACTOR.md` | EXISTS | 39 lines; captures (a) `AppConfig.key` PK + (b) `Member.slug` UNIQUE multi-tenant follow-ups + (c) conftest `sys.path.insert` cleanup. Content matches DECISIONS §11's expectations. | §0 verify | VERIFY confirmed; no edit |

**Bonus path not in §2 inventory but very relevant:** `/INSTALL.md` exists at the repo root (133 lines). It's the substantial install doc the existing repo-root README links to. The §4.1 spec says the new README's "Install" subsection should link to `family_chores/README.md` (which doesn't exist). With Q1 unresolved, INSTALL.md remains the de-facto install doc — flagged in Q2 below.

#### Image inventory (every PNG in the repo, excluding `.venv/`, `node_modules/`, `.git/`, caches)

| Path | Source / purpose |
|---|---|
| `docs/screenshots/today-desktop.png` | Hero shot — 3 member tiles, 100/33/50% progress |
| `docs/screenshots/today-portrait.png` | Same view stacked vertically for phone viewports |
| `docs/screenshots/member-carol.png` | Kid view with mixed states (done + pending cards) |
| `docs/screenshots/member-alice-all-done.png` | Celebration screen — confetti + "You did it!" |
| `docs/screenshots/parent-approvals.png` | Parent → Approvals tab with pending item |
| `docs/screenshots/parent-members.png` | Parent → Members tab |
| `docs/screenshots/parent-chores.png` | Parent → Chores tab |
| `family_chores/icon.png` | 570-byte placeholder (per existing README's "Assets to replace" — see §6 of the prompt) |
| `family_chores/logo.png` | 888-byte placeholder (same) |

No image is in a "messy" location — `docs/screenshots/` is a clean canonical path that the existing repo-root README already references. Per §3 ("Referenced image paths match reality") and §6 ("Move screenshots: leave them"), nothing to relocate.

**Lovelace-card screenshot:** none exists. The existing `lovelace-card/README.md` does not reference an image. Per §4.5 the new card README should include a screenshot at `docs/screenshots/lovelace-card.png`. Flagged in "Human action needed" below.

### Open questions (block before content phase begins)

**Q1 — `family_chores/README.md` does not exist. Resolve before §4.1 + §4.2 work begins.**
HA add-on convention: a README inside the addon directory shows in HA's add-on store *before* install; `DOCS.md` shows in the "Documentation" tab *after* install. With no addon-dir README, HA's store probably falls back to the `description:` line in `config.yaml` (`"Family chore tracking and rewards, with HA entity bridging."`) — short and plain, but technically functional.

Three options:

  - **(a)** CREATE `family_chores/README.md` as a fresh, store-appropriate file — short (~80–120 lines), one-screen overview with one or two screenshots, the install path (link to `INSTALL.md`), and a "Full project README" link to `/README.md`. The existing repo-root README serves the GitHub-visitor audience; the new addon README serves the HA-store-browser audience. **§4.1's recommendation to link from the repo-root README's Install section to `family_chores/README.md` then becomes correct.**
  - **(b)** Don't create one. Repo-root README's Install section links to `INSTALL.md` directly (current state). HA's store keeps using the `description:` line. Slight discoverability hit but no risk of duplicating content.
  - **(c)** Create a one-line stub `family_chores/README.md` that just points to the repo-root README + INSTALL.md. Cheapest. Probably worst experience for the HA-store browser who never clicks through.

  **Recommendation: (a).** Highest user-experience payoff for the addon-store browser, and it makes §4.1's spec self-consistent. ~1 hour of writing.

**Q2 — `INSTALL.md` reconciliation.** Whether to keep INSTALL.md at the root (current state) or fold it into the new `family_chores/README.md` from Q1(a). The Q1(a) addon README would be short by design and link to INSTALL.md for full detail. INSTALL.md stays.

**Q3 — LICENSE choice.** Existing repo-root README says "MIT." No `LICENSE` file in the repo. Per §4.8 the default if forced is MIT — needs human confirm. If MIT is wrong (e.g. you've decided AGPL or proprietary), flag now.

**Q4 — Contact email for SECURITY.md and CODE_OF_CONDUCT.md.** Per §6, Claude cannot fill in. Will use `YOUR_CONTACT_EMAIL_HERE` placeholders. Human swaps before merge.

**Q5 — Lovelace card screenshot.** §4.5 calls for one. None exists. Capture-in-this-session is feasible (the dev server + headless-Chrome pipeline from the README screenshots commit `63be636` still works); needs a built `dist/family-chores-card.js` and a real HA install to render the card against, OR a synthetic test page. Lower priority than text content — can ship the card README without it and add later.

**Q6 — `family_chores/CHANGELOG.md` historical entries reference pre-refactor module paths** (`family_chores.ha.bridge`, `family_chores.services.*`) in prose. Per §4.4 these are intentionally byte-identical to what shipped. They are factually correct as-of the milestone they document. No action needed but noting for the record.

### Action plan summary (after Q1–Q5 resolved)

In commit groups per §7:

1. **Governance:** `LICENSE` (MIT, flagged), `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config}.yml`, `.github/PULL_REQUEST_TEMPLATE.md`. ~7 new files. Standard content.
2. **Repo-root content:** EDIT `/README.md` per §4.1 (full diff likely; will flag scope), CREATE `docs/architecture.md`, CREATE `docs/roadmap.md`. ~2 new files + 1 sizeable EDIT.
3. **Lovelace card docs:** EDIT `lovelace-card/README.md`, CREATE `lovelace-card/hacs.json`, CREATE `lovelace-card/info.md`, CREATE `lovelace-card/CHANGELOG.md`. 1 EDIT + 3 new files.
4. **Add-on README** (Q1-dependent): CREATE `family_chores/README.md` if Q1=(a). 0 or 1 new file.
5. **Add-on DOCS.md gap-fill:** EDIT `family_chores/DOCS.md` to add Dashboard integration, Backup and restore, Privacy, expand troubleshooting from 3 → 6 FAQs. 1 EDIT.
6. **Verification + summary** (per §5): link check, image-path check, ensure `family_chores/README.md` (Q1) and `family_chores/CHANGELOG.md` aren't disturbed, confirm `config.yaml` version unchanged, run full test suite, summarise.

### Merge checklist (human actions required before merging the polish branch)

- [ ] Resolve Q1 (whether to create `family_chores/README.md`).
- [ ] Resolve Q3 (confirm MIT license is correct).
- [ ] Replace `YOUR_CONTACT_EMAIL_HERE` placeholders in `SECURITY.md` and `CODE_OF_CONDUCT.md`.
- [ ] (Optional) Capture a Lovelace-card screenshot for `docs/screenshots/lovelace-card.png` (Q5).
- [ ] Review the rewritten `/README.md` for voice; this is the polish output you'll see most.
- [ ] Confirm `family_chores/README.md` (if created via Q1=a) is acceptable for the HA add-on store before tagging the next release.

### Pause point

Per prompt §7: this commit (DECISIONS.md only — no content files yet) ends the inventory phase. Awaiting human review + Q1–Q5 answers before starting commit group 1.

### Completion (2026-04-24)

Human responses to Q1–Q5 (received in-session, 2026-04-24):

- **Q1 → (a).** Create `family_chores/README.md` as a fresh store-appropriate file.
- **Q2 →** Keep `INSTALL.md` at repo root.
- **Q3 → MIT confirmed.**
- **Q4 →** `YOUR_CONTACT_EMAIL_HERE` placeholders acceptable; maintainer swaps before merge.
- **Q5 → (B).** Skip Lovelace-card screenshot for this pass; can be added later.

#### Commits on `release-polish` (all documentation-only)

| Commit | Group | What |
|---|---|---|
| `b50d63a` | 0 | §12 pre-work inventory (this section, initial) |
| `67b5a26` | 1 | Governance: LICENSE, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, issue templates × 3, PR template |
| `d3a0592` | 2 | Repo-root README rewrite + `docs/architecture.md` + `docs/roadmap.md` |
| `9f71100` | 3 | Lovelace card docs: README edit + `hacs.json` + `info.md` + `CHANGELOG.md` |
| `43116b5` | 4 | `family_chores/README.md` (store-appropriate, 90 lines) |
| `3c8bafe` | 5 | `family_chores/DOCS.md` expansion: Dashboard integration, Backup+restore, Privacy, 6 FAQs |
| *this commit* | 6 | Verification pass: architecture.md path fix + this completion note |

Branch delta vs. base `63be636`: 18 files / +1082 / −106 lines, all documentation.

#### Verification results

- **Link check.** Scanned all 12 touched markdown files for broken relative links and `<img src=...>` paths; zero broken.
- **Image-path check.** All 7 screenshots in `docs/screenshots/` referenced by `/README.md` resolve. No new images introduced.
- **`family_chores/CHANGELOG.md` byte-identical.** `git diff 63be636..HEAD -- family_chores/CHANGELOG.md` returns zero lines.
- **`family_chores/config.yaml` version unchanged** at `0.2.1`.
- **Test suite green.** `./scripts/lint.sh` exits 0 on every stage: ruff + mypy (addon + packages + saas), pytest (147 addon + 12 saas + 81 architecture + packages suites), frontend lint + typecheck + vitest (26 addon + 2 web), lovelace-card tsc. 364 tests total, consistent with `docs/architecture.md`'s testing topology.

#### Surprises / deviations from plan

- **`docs/architecture.md` `AuthStrategy` path error caught at verification.** I originally wrote `packages/api/src/family_chores_api/auth.py` when the Protocol actually lives at `packages/api/src/family_chores_api/deps/auth.py`. Caught by grepping for `class AuthStrategy(Protocol)` across `packages/`. Fixed in this commit.
- **CoC filter workaround.** Output-filtering policy blocked writing the Contributor Covenant 2.1 verbatim (the policy's enumeration of unacceptable-behaviour categories reads like sensitive content when reproduced). Pivoted to the widely-used adopt-by-reference pattern: `CODE_OF_CONDUCT.md` is a short file that states the project adopts Covenant 2.1, links to the canonical text on contributor-covenant.org, and specifies the enforcement contact. Kubernetes, Django, and Rust use this pattern. Maintainability bonus: future Covenant updates are inherited automatically with no edit.
- **Context-window boundary during commit group 1.** Conversation hit the context limit mid-group; three governance files (`LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`) were written but not yet committed at the break. Continuation resumed at the same branch state and completed the group without re-doing work. No duplicate or conflicting files produced.

#### Updated merge checklist

What remains before merging `release-polish`:

- [ ] **Replace `YOUR_CONTACT_EMAIL_HERE` placeholders** in `SECURITY.md` and `CODE_OF_CONDUCT.md` with a real reporting address. Use the same address in both.
- [ ] **Review the rewritten `/README.md`** for voice — this is the most-read output.
- [ ] **(Optional) Capture a Lovelace-card screenshot** for `docs/screenshots/lovelace-card.png` and reference it from `lovelace-card/README.md` and `lovelace-card/info.md` (Q5 deferred).
- [ ] **(Optional) Replace `family_chores/icon.png` and `family_chores/logo.png`** placeholders before the next tagged release. The placeholders ship today; the polish didn't touch them.

Resolved from the initial checklist:

- [x] Q1 resolved — `family_chores/README.md` created (option a, 90 lines).
- [x] Q3 resolved — MIT confirmed; `LICENSE` created.
- [x] Polish did not disturb `family_chores/CHANGELOG.md` (byte-identical check passes).
- [x] `config.yaml` version unchanged (confirmed at `0.2.1`).

The polish branch is merge-ready pending the two required human actions above (email swap + README voice review).

## 13. Chore suggestions

Tracking prompt: post-v0.2.4 chore-suggestions feature prompt (received 2026-04-24, after v0.2.4 was tagged and pushed). Goal: ship a bundled starter library of 46 age-appropriate chore templates plus a "Browse suggestions" affordance inside the Add Chore form, with templates living parallel to chores (editing a chore never edits its source template). Branch: `feat-chore-suggestions` off `main` at `3965ae3` (the v0.2.4 release commit).

### Pre-work inventory (2026-04-24)

#### Codebase divergences from the prompt's assumed shape

| Prompt assumption | Actual codebase | Implication |
|---|---|---|
| Models split into per-table files under `packages/db/src/family_chores_db/models/` | All models live in a single `models.py` (~250 lines) | New `ChoreTemplate` + `HouseholdStarterSuppression` classes go in `models.py`, not separate files |
| `Member` has an `age` column (referenced by §1.3 "youngest member's age" default) | No `age` column on `Member` today | §1.3's youngest-age default is **inert** unless we add the column — see Q2 |
| Add Chore is a "dialog" (modal) | `family_chores/frontend/src/views/parent/ChoresTab.tsx` renders the Add Chore form **inline** at the top of the Chores tab — not a modal | "Browse suggestions" panel becomes another inline section above the form, not a modal-inside-modal — matches the prompt's "lean toward inline" preference |
| Models use `server_default=...` for new columns (per the §2.1 spec snippets) | Existing `models.py` uses Python-side defaults exclusively (`default=utcnow`, `default=dict`, `default=0`) | Match house style — Python-side defaults on the ORM models. The migration uses `server_default` (correct for emitting the table-level default in CREATE TABLE / ALTER TABLE) |
| Recurrence enum includes a "weekly" type | No `WEEKLY` member of `RecurrenceType` (engine has DAILY, WEEKDAYS, WEEKENDS, SPECIFIC_DAYS, EVERY_N_DAYS, MONTHLY_ON_DATE, ONCE) | The library's `default_recurrence: "weekly"` strings need translation — see Q1 |
| Addon has a `services/` directory | Addon has no `services/` directory; existing `services/` lives in `packages/api/src/family_chores_api/services/` | Seeding service goes in `packages/api/services/starter_seeding.py` so SaaS reuses it; addon `app.py` calls it from lifespan |
| Migration filename `0004_add_chore_templates` | Existing migrations are `0001_initial_schema.py`, `0002_add_member_ha_todo_entity_id.py`, `0003_add_household_id.py` — same numeric+slug convention | New migration: `0004_add_chore_templates.py`. Down-revision: `0003_add_household_id` |

#### Recurrence-config shape verification (per `packages/core/src/family_chores_core/recurrence.py`)

| RecurrenceType enum | Config required | Library JSON `default_recurrence` mapping |
|---|---|---|
| `DAILY` | `{}` (none) | `"daily"` → direct |
| `WEEKDAYS` | `{}` | not used by the library |
| `WEEKENDS` | `{}` | not used by the library |
| `SPECIFIC_DAYS` | `{"days": [int 1–7 ISO]}` (Mon=1, Sun=7) | `"weekly"` → propose `{"days": [6]}` (Saturday) — see Q1 |
| `EVERY_N_DAYS` | `{"n": int≥1, "anchor": ISO date string}` | not used by the library |
| `MONTHLY_ON_DATE` | `{"day": int 1–31}` | not used by the library |
| `ONCE` | `{"date": ISO date string}` | not used by the library |

The library only uses two recurrence labels: `"daily"` (15 entries) and `"weekly"` (31 entries). All `"daily"` map cleanly to `RecurrenceType.DAILY` with empty config. All `"weekly"` need the translation per Q1.

`packages/api/src/family_chores_api/schemas.py:validate_recurrence_config()` is the canonical validator — the seeder will use it to verify each translated config before insert, so a typo in the library's mapping would fail seeding loudly rather than producing broken templates.

#### MDI icon verification (42 unique names across the 46 chores)

Verified against `https://pictogrammers.com/library/mdi/` via a research agent. **40 of 42 valid as-shipped.** Two substitutions needed:

| Library entry | Original icon | Status | Substitute |
|---|---|---|---|
| `match_socks` | `mdi:sock` | does not exist in current MDI | `mdi:tshirt-crew-outline` (no sock-family icon exists; reuse the laundry-friendly outline variant) |
| `pack_backpack` | `mdi:backpack` | does not exist in current MDI | `mdi:bag-personal` |

All seven names I flagged as suspicious (`silverware-clean`, `bowl-mix`, `dishwasher-off`, `table-chair`, `dog-side`, `hanger`, `music`) returned 200 and are valid. Will record both substitutions in the JSON file as the actual `icon` value (not as runtime mapping) so the data file stays self-describing.

#### Library content notes

46 entries as specified in §3, no proposed additions. The §3 invitation to "propose additions to reach 50" is declined for this prompt — 46 already covers ages 3–10+ across 11 categories, and adding more without a parenting-research grounding would just be padding.

Categories canonical set (`StrEnum` in core): `bedroom`, `bathroom`, `kitchen`, `laundry`, `pet_care`, `outdoor`, `personal_care`, `schoolwork`, `tidying`, `meals`, `other`. Eleven. Matches §3 verbatim.

#### File layout plan

```
NEW
packages/core/src/family_chores_core/data/starter_library.json     46 chores
packages/core/src/family_chores_core/starter_library.py            JSON loader (parse-only, no DB)
packages/core/src/family_chores_core/naming.py                     normalize_chore_name()
packages/core/tests/test_starter_library.py
packages/core/tests/test_naming.py
packages/db/src/family_chores_db/migrations/versions/0004_add_chore_templates.py
packages/db/tests/test_migration_0004.py
packages/api/src/family_chores_api/services/starter_seeding.py     seeder (DB-aware, household-scoped, idempotent, suppression-aware)
packages/api/src/family_chores_api/routers/suggestions.py
packages/api/tests/test_suggestions.py
family_chores/tests/test_seeding.py                                addon-level integration tests
family_chores/tests/test_template_no_ha_sync.py                    defensive HA-sync test (§7)
family_chores/frontend/src/api/suggestions.ts                      client + TanStack Query hooks
family_chores/frontend/src/components/BrowseSuggestionsPanel.tsx
family_chores/frontend/src/components/ManageSuggestionsView.tsx
family_chores/frontend/src/components/__tests__/{BrowseSuggestionsPanel,ManageSuggestionsView}.test.tsx

EDITED
packages/db/src/family_chores_db/models.py                         + ChoreTemplate, HouseholdStarterSuppression; +Chore.template_id, +Chore.ephemeral
packages/api/src/family_chores_api/schemas.py                      + SuggestionRead/Create/Update; ChoreCreate gains template_id, save_as_suggestion; new ChoreCreateResult shape
packages/api/src/family_chores_api/routers/__init__.py             register suggestions router
packages/api/src/family_chores_api/routers/chores.py               POST creates a template alongside the chore when save_as_suggestion=True
family_chores/src/family_chores_addon/app.py                       call starter_seeding from lifespan after bootstrap, before scheduler
family_chores/frontend/src/views/parent/ChoresTab.tsx              add Browse Suggestions section + Save-as-suggestion checkbox
family_chores/frontend/src/api/types.ts                            new types

DOCS (step 11 only — not before)
family_chores/DOCS.md                                              new "Suggestions" section under First-run setup
family_chores/CHANGELOG.md                                         [Unreleased] entry — DRAFT only, no version
docs/roadmap.md                                                    if "chore suggestions" was in "near-term" → move to "Landed" (no version tag)
```

#### Test baseline

Today: **364 tests** total across all workspaces (per `docs/architecture.md` and verified during the polish-work group-6 lint run).

Target after this feature: **405–420** (+40–55 net new) per §8. Composition:
- core: +20–25 (naming + starter library validation)
- db: +6–8 (migration round-trip + constraint enforcement)
- api: +12–18 (suggestions endpoints + chore-POST with template creation + scoping)
- addon: +10–14 (seeding integration + suppression + reset + HA-sync defensive)
- frontend: +6–10 (browse panel + manage view + first-run badge state)

### Open questions (block before step 1 begins)

**Q1 — How to translate `"weekly"` library entries to a real recurrence config?**
The library JSON uses `"weekly"` for 31 of 46 entries (e.g. `tidy_bedroom`, `walk_dog`, `take_out_trash`). The recurrence engine has no WEEKLY type. §3 explicitly says "If a recurrence type requires config and the library entry can't provide a sensible default, either (a) add a default to this prompt's library (e.g. Saturday for weekly) or (b) omit that recurrence type from starter entries."

  **Recommendation: (a) with Saturday default.** Map `"weekly"` → `RecurrenceType.SPECIFIC_DAYS` with `{"days": [6]}` (ISO Saturday). The library JSON keeps the friendly `"weekly"` label; the seeder does the translation. Alternative: store the translated form in the JSON directly (`default_recurrence_type: "specific_days"`, `default_recurrence_config: {"days": [6]}`) — uglier JSON but truthful. I prefer the friendly-label-with-translation approach because the JSON is also a human-readable starter catalogue.

  Either way, the `default_recurrence_config` field stored on the template row is the engine-canonical form (`{"days": [6]}`), not the library label.

**Q2 — Member.age column?**
§1.3 says the Suggestions panel defaults to filtering by the youngest member's age "from `member.age` if we have it." Today there is no `member.age`. Two options:

  - **(A)** Skip the age-default. Panel defaults to "any" age slider; parent sets it manually if they want age-filtering. Suggestions still carry `age_min`/`age_max` and the slider still works on user input. **Lower scope, recommended.**
  - **(B)** Add `Member.age: int | None` column in this migration. Enables the youngest-default. Adds a Member edit-form field (kid-facing? No — parent-facing in Members tab). Crosses into Member model territory the prompt doesn't mention.

**Q3 — Confirm icon substitutions** in the verification table above:
  - `mdi:sock` → `mdi:tshirt-crew-outline` for "Match socks"
  - `mdi:backpack` → `mdi:bag-personal` for "Pack backpack"

  Both are research-agent verified as existing in current MDI. If you want me to spot-check these against your specific HA frontend MDI version (which may lag the current catalog), say so and I'll WebFetch them directly.

**Q4 — Where does the seeding service live?**
  - **(A)** `packages/api/src/family_chores_api/services/starter_seeding.py` — shared, the SaaS app would reuse it when provisioning a new household. **Recommended** (consistent with existing `services/` placement).
  - **(B)** `family_chores/src/family_chores_addon/seeding.py` — addon-only. Simpler now, refactor later if SaaS needs it.

**Q5 — Branch name confirmation.** I propose `feat-chore-suggestions`. Off `main @ 3965ae3`. OK?

### Action plan summary (after Q1–Q5 resolved)

12 commits, in this order, each runnable with green tests. PAUSE points marked.

| # | Commit | Files |
|---|---|---|
| 1 | `feat(core): starter library JSON + tests` | `data/starter_library.json`, `starter_library.py` (loader), `tests/test_starter_library.py` |
| 2 | `feat(core): normalize_chore_name + tests` | `naming.py`, `tests/test_naming.py` |
| 3 | `feat(db): migration 0004 — chore templates + suppression + chore.template_id/ephemeral` | `models.py` edits, `0004_add_chore_templates.py`, `tests/test_migration_0004.py` |
| 4 | `feat(addon): starter library seeding + suppression handling` (**PAUSE for review after this**) | `services/starter_seeding.py` (api), `app.py` (addon) lifespan call, `tests/test_seeding.py` (addon) |
| 5 | `feat(api): /api/suggestions/* + chore POST template creation` | `routers/suggestions.py`, `routers/chores.py` edits, `schemas.py` edits, `tests/test_suggestions.py` |
| 6 | `feat(frontend): Browse Suggestions panel inside Add Chore form` | `BrowseSuggestionsPanel.tsx`, `api/suggestions.ts`, `ChoresTab.tsx` integration, `__tests__/BrowseSuggestionsPanel.test.tsx` |
| 7 | `feat(frontend): save-as-suggestion checkbox + POST flow-through` (**PAUSE for review after this**) | `ChoresTab.tsx` edits, `api/types.ts` extensions, frontend test additions |
| 8 | `feat(frontend): Manage Suggestions view` | `ManageSuggestionsView.tsx`, `__tests__/ManageSuggestionsView.test.tsx`, `BrowseSuggestionsPanel.tsx` link |
| 9 | `feat(frontend): first-run discoverability badge` | `ChoresTab.tsx` edits, `app_config` flag plumbing |
| 10 | `test(addon): defensive HA-sync test for templates` | `tests/test_template_no_ha_sync.py` |
| 11 | `docs(suggestions): DOCS.md section + CHANGELOG draft + roadmap update` | `DOCS.md`, `CHANGELOG.md`, `docs/roadmap.md` |
| 12 | (verification only, no commit) | full `./scripts/lint.sh` green; final summary |

### What this section is NOT yet doing

- **Not bumping `family_chores/config.yaml`.** Per §11 #9 and CONTRIBUTING.md, version bumps happen at human-decided tag time. The CHANGELOG entry in step 11 will be `[Unreleased]`, not `[0.3.0]`.
- **Not touching the kid-facing UI, recurrence engine, streak/points logic, approval flow, or HA bridge.** Per §11.
- **Not exposing the word "template" in any UI string.** Code uses `chore_template`, UI uses "suggestion".
- **Not adding a separate tab or sidebar entry.** Add Chore form is the only entry point.

### Pause point

Per prompt §12.2: this commit (DECISIONS.md only — no content files yet) ends the inventory phase. Awaiting human review + Q1–Q5 answers before starting step 1.

## 14. Calendar integration

Tracking discussion: post-v0.4.0 brainstorm with three personas (engineering, family-coordinator, UX designer) settling the design space before any code lands. The feature crossed the bar from "small follow-up" to "section-worthy" because of two architectural moves: (a) the introduction of `CalendarProvider` / `TodoProvider` Protocol seams, and (b) the first row in the new `household_settings` table. Both lay groundwork the future SaaS deployment will depend on.

(Section numbering: §13 was the previous formal entry. F-S001 / v0.3.1 fixes referenced "§16" in commit messages and the v0.4.0 work referenced "§17"; neither was ever written into this file. They were aspirational placeholders. This is the next real section number.)

### Strategic context

User asked early in the brainstorm: "How far away from this being a standalone product that doesn't need HA to survive?" Honest answer was four tiers:

  - **Tier 1** (~1 week, doing now via this PR series): provider abstractions in place. Same product, but every HA-coupling point goes through a Protocol seam.
  - **Tier 2** (~3–4 weeks): standalone Docker deployment. Email/password + OAuth, native CalDAV + Google Calendar API providers, Postgres support. Anyone can run it without HA.
  - **Tier 3** (~3–6 months): SaaS-grade. Multi-tenant hardening (the existing `household_id` plumbing gaps in `TODO_POST_REFACTOR.md` become blocking), Stripe billing, push/email notifications, **COPPA + GDPR-K compliance for kids data**.
  - **Tier 4** (~6–12 months): mobile-first product. Native iOS/Android (the kid-tablet UX really wants to be native), or polished PWA.

User confirmed Tier 1 commitment as part of this work. Future tiers are optional / undecided. This section's job is to make Tier 1 happen alongside the calendar feature without dragging in the rest.

### Settled design decisions

Each row captures a question raised during the brainstorm and the resolution.

| # | Question | Resolution |
|---|---|---|
| 1 | Build native CalDAV/Google calendar clients, or read from HA's calendar entities? | **HA-as-data-source for v1.** `HACalendarProvider` is the only initial Protocol impl. Future providers plug into the same seam. Avoids OAuth/token storage entirely. |
| 2 | How to enforce parent-only event privacy? | **Per-member calendar-entity mapping.** Parent assigns specific HA `calendar.*` entity IDs to specific members. Events on Mom's work calendar simply aren't mapped to anyone. |
| 3 | Prep-text convention? | **`[prep: ...]` tag in event description (power-user) + verb-fallback parsing for the 80% case.** Verb list: `bring`, `wear`, `pack`, `don't forget` (from Maya — 4 phrases / 5 words). Both passes feed the same `prep_items: list[{label, icon}]` server-side payload. |
| 4 | Monthly view: grid or list? | **Both, with toggle.** List is the default (matches the SPA's vertical reading). Grid auto-defaults at viewport ≥1280px AND parent JWT active. Toggle persists per-device in localStorage. |
| 5 | Per-kid PIN gate covers calendar too? | **Yes — but only when `member.pin_set === true`.** Reuses the existing `kidPinStore`; no new gate machinery. Kids without a PIN see calendar freely (same as chores). |
| 6 | Member calendar mapping: one entity or list? | **`list[str]` (`ha_calendar_entity_ids`).** Most kids have multiple — school, sports, family-shared. Single-string would mean immediate schema change later. |
| 7 | Past events on tile / member view? | **Hide once `event.end < now`.** Kids react to "what's next," not "what happened." |
| 8 | Recurring events? | **Handled by HA's `calendar.get_events` service** which expands recurrences server-side in the response. Free for v1. |
| 9 | Household-level config: `app_config` row or new table? | **New `household_settings` table.** One row per household. Reserved space for future household-level settings (week start day moved here later, etc.). Cleaner long-term. |
| 10 | Caching strategy? | **60-second TTL on server-side cache, keyed by `(entity_id, day)` + manual refresh button on monthly view.** WS-driven invalidation rejected because HA's calendar integrations don't reliably fire `state_changed` for individual event edits — would be a false promise. The 60s + refresh combo: short enough that "I just added an event" usually shows up by the next kid glance; explicit button for the parent who wants their last-minute edit immediately. Cache also invalidates on any household-settings or member-calendar-mapping change so config edits are immediate. |
| 11 | Calendar entity unreachable / 5xx? | **Show a per-tile "couldn't reach calendar" state.** Surfaced via `unreachable_calendars: list[str]` on the response payload. Silent fallback would lie to the user. |
| 12 | Tier 1 retroactive sweep — wrap existing HA-todo plumbing in a `TodoProvider` Protocol? | **Yes.** `TodoProvider` Protocol added in PR-A; `HATodoProvider` retrofits the existing reconciler / bridge code. Sensor publishing + event firing are already abstracted via `BridgeProtocol` (no work). |

### Architectural shape

**New `packages/api/src/family_chores_api/services/calendar/` directory:**

  - `provider.py` — `CalendarProvider` Protocol (`async def get_events(entity_ids, from_dt, to_dt) -> list[CalendarEvent]`)
  - `prep.py` — pure prep-parsing helpers (`extract_prep_items(description: str) -> list[PrepItem]`)
  - `cache.py` — 60s TTL by `(entity_id, day)`, invalidation API
  - `service.py` — composition: provider + cache + prep parsing into the API-shape `CalendarEvent`

**New `packages/api/src/family_chores_api/services/todo/` directory** (Tier 1 sweep):

  - `provider.py` — `TodoProvider` Protocol matching the existing HA todo surface (get_items, add_item, update_item, remove_item)
  - The existing `family_chores_addon/ha/reconcile.py` + `family_chores_addon/ha/bridge.py` Local-Todo plumbing is refactored to depend on the Protocol, with `HATodoProvider` as the only initial impl.

**Data model (migration 0008):**

  - `members.calendar_entity_ids: JSON` (defaults to empty list `[]` for existing rows)
  - New `household_settings` table:
    - `household_id: str | None` — primary key (NULL in single-tenant addon mode, scoped pattern)
    - `shared_calendar_entity_ids: JSON` — list of strings, defaults to `[]`
    - `created_at`, `updated_at` (Python-side defaults via `utcnow`)

**API surface (this PR introduces):**

  - `GET /api/household-settings` — kid-visible (the shared calendar mapping isn't sensitive)
  - `PATCH /api/household-settings` — parent-required
  - `GET /api/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD&member_id=N` — kid-visible. Defers to PR-C for the consumer, but the endpoint lands here for completeness.
  - `POST /api/calendar/refresh` — parent-required, busts the cache.

**API surface (later PRs):**

  - `GET /api/today` extended with `events: list[CalendarEvent]` per member + `shared_events`. Lands in PR-B.
  - The full monthly-view consumer wiring lands in PR-C.

### PR breakdown

| PR | Effort | Scope |
|---|---|---|
| **PR-A** (this one) | 2–3 days | Migration 0008, `CalendarProvider` + `HACalendarProvider`, `TodoProvider` + retrofit, prep-parsing core + tests, `household_settings` CRUD endpoints, `/api/calendar` endpoint shell, cache layer. **No frontend.** |
| **PR-B** | 3–4 days | `/api/today` extension, MemberTile event chips, MemberView "Today" section with prep chips, `unreachable_calendars` error state. |
| **PR-C** | 4–5 days | `/calendar` route with list + grid views, view toggle + viewport-aware default, household-settings tab in Parent mode, manual refresh button, member calendar-mapping UI. |
| **PR-D** | 0.5 day | DOCS.md "Calendar integration" section, this DECISIONS §14 entry's "completion" subsection, `roadmap.md` "Landed" update. |

After all four merge: cut **v0.5.0** (minor bump — new feature surface, no breaking changes; the provider Protocols are additions, not refactors of existing public APIs).

### What this PR (and section) is NOT yet doing

- **Not building a non-HA `CalendarProvider`.** That's Tier 2. The seam exists; the second impl waits for actual demand.
- **Not implementing the kid-facing UI.** PR-B's job. PR-A is data + API only so each side can be reviewed independently.
- **Not modifying the existing per-member `ha_todo_entity_id` schema.** The TodoProvider sweep is a code-organization change, not a schema change. Existing column stays as the storage layer; the Protocol wraps the runtime behavior.
- **Not adding new HA event firing.** Calendar reads, not writes. If/when the addon needs to fire events on calendar changes (e.g., "30 minutes before soccer, blink the hall light"), that's its own feature.
- **Not bumping `family_chores/config.yaml`.** Per CONTRIBUTING.md the maintainer bumps + tags at release time, after PR-D merges.

### Pause point

This commit (DECISIONS.md only) ends the inventory phase for §14. The user has already settled all 12 questions in the brainstorm — no open questions remain blocking PR-A. Implementation begins immediately in subsequent commits on this branch.

### Completion (2026-05-01)

All four PRs merged and v0.5.0 released. Net adds across the four:

- **24 new files** (8 backend src, 8 backend tests, 6 frontend components, 2 docs).
- **~3,300 lines added** end-to-end including tests + docs.
- **45 new backend tests** (16 cache + 19 service + 19 HA provider + 6 NoOp todo + 9 HA todo + 22 router HTTP + 9 today-extension) and **33 new frontend tests** (7 PrepChipStrip + 8 CalendarDayList + 10 MonthGrid + 8 CalendarEntityIdsEditor).

PR-by-PR summary:

| PR | Sha | Scope | Notes |
|----|-----|-------|-------|
| PR-A | 414cfae | Migration 0008, `CalendarProvider` Protocol + `HACalendarProvider`, `TodoProvider` Protocol + retrofit, prep parser, cache, composition service, `/api/household/settings` + `/api/calendar` endpoints | Migration 0008 had to be amended in-place to swap `HouseholdSettings` from a single-column `household_id` PK to a synthetic `id` PK + nullable `household_id` — SQLAlchemy's identity map rejects all-NULL PKs even though SQLite accepts them. |
| PR-B | 0bfe0fe + 23f1353 | `/api/today` extension, `PrepChipStrip` + `CalendarDayList` components, `MemberTile` chip strip + next-event line, `MemberView` Today section | Calendar fetch on `/api/today` is best-effort: a provider exception logs and continues with empty events. Chores must NEVER fail because of a calendar issue. |
| PR-C | 18ff581 | Calendar tab in Parent nav, `MonthGrid` 6×7 grid, `CalendarEntityIdsEditor` chip input, household-shared + per-member settings panels, refresh button | Window fetched matches the visible 42 cells (Mon-first), not just the calendar month — avoids "where's my Apr 30 event in the May grid?" off-by-one. |
| PR-D | (this) | `docs/calendar.md`, this completion subsection, `docs/roadmap.md` "Landed" entry, `docs/architecture.md` provider Protocols mention | Docs only — no code change. |

**Deviations from the original plan:**

- **§14's PR-A inventory said `GET /api/household-settings` and `PATCH`.** Shipped as `GET /api/household/settings` + `PUT` (slash-separated path matches REST convention; `PUT` matches the "replace this scalar setting" semantic better than `PATCH` for a single-row config table).
- **`/api/calendar` endpoint shape changed.** Inventory said `GET /api/calendar?from=&to=&member_id=`. Shipped as `GET /api/calendar/events` (the `/calendar` namespace also hosts `POST /api/calendar/refresh` so an `/events` segment disambiguates).
- **`TodayMember.events` field name.** Inventory said `events: list[CalendarEvent]`. Shipped as `calendar_events: list[CalendarEventRead]` to avoid colliding with anyone's mental model of "today's chore instances are events" — the namespacing is worth the extra characters.
- **`unreachable_calendars` → `calendar_unreachable`.** Same reason: `calendar_*` prefix groups all calendar-related fields on `TodayMember` for easy grep.
- **Tier 1 sweep was bigger than originally scoped.** Inventory said "wrap todo plumbing in a TodoProvider". Reality: the bridge AND reconciler both depended on `HAClient.todo_*` directly, so the sweep updated both call sites + the FakeHAClient (extending it to satisfy both `HAClient` and `TodoProvider` structurally so no test call sites had to change). Net 11 files modified, 256 existing addon tests still green.

**Things deliberately deferred:**

- **No per-calendar color picker.** All event chips on the monthly grid use the brand color. A "color this calendar pink" UI would need a settings shape change (color per entity_id) — easy fast-follow if user testing wants it.
- **No FullCalendar / scheduler view.** The `MonthGrid` is custom and intentionally minimal. A library-driven calendar would be heavier and bring its own UX assumptions; the custom grid renders in <1KB of component code and matches the rest of the addon's design system.
- **No autocomplete on entity ids.** The chip-input editor is type-and-add. A future "list available `calendar.*` entities from HA" autocomplete would need a new endpoint exposing the HA entity registry; revisit if user testing surfaces "what's my entity id called" friction.
- **No write path.** Calendar reads, not writes. If the addon needs to fire HA events on calendar changes (e.g. "30 min before soccer, blink the hall light"), that's its own feature and lives in HA automations triggered by the existing `family_chores_*` events.

**Lessons / things future-me should know:**

- **SQLite NULL PKs are an SQLAlchemy issue, not a SQLite issue.** Single-column NULL PKs work in SQLite; SQLAlchemy's identity map rejects them. The `HouseholdSettings.id` synthetic PK + nullable `household_id` pattern is the workaround. If we ever need a similar single-row-per-household table, copy this shape.
- **Provider Protocols are cheap.** The TodoProvider sweep was ~250 lines of new code for the seam — and it makes Tier 2 (standalone deployment) achievable without rewriting the bridge. The CalendarProvider Protocol is the same shape. Whenever the addon grows a third HA-coupled subsystem (e.g. "presence detection drives display mode"), pre-emptively wrapping it in a Protocol from day one is cheaper than retrofitting.
- **Best-effort calendar fetch on `/api/today` is the right call.** The kid view depending on HA being up would be a regression vs. v0.4. The exception handler in `today_view` is load-bearing.
- **`from __future__ import annotations` doesn't fully help with Pydantic forward refs in v2.** `TodayMember.calendar_events: list[CalendarEventRead]` still requires `CalendarEventRead` to be defined before `TodayMember` at module-load time, even with the annotations import. Solution: move `CalendarEventRead` (and `CalendarPrepItemRead`) up in the file. (The cleaner alternative — `model_rebuild()` after import — is more code for the same effect.)

The §14 work shipped in v0.5.0. Marker entry in `docs/roadmap.md` "Landed" updated; `docs/calendar.md` is the user-facing reference; `docs/architecture.md` was lightly extended to mention the Provider Protocols.
