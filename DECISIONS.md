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

### Stop-line

Plan is drafted. **Pausing here for user review per prompt §11.** Once approved, I'll load `TodoWrite`, create one todo per step (1–13), and start with step 1 (scaffolds + workspace tooling).
