# DECISIONS — Family Chores add-on

Living design notes. New entries go at the top of each section; significant changes get a dated entry in §10 Changelog.

---

## 0. Project snapshot

**What we're building:** a Home Assistant Add-on (single Docker container, Ingress-served FastAPI + React SPA) that tracks family chores, rewards, and streaks. SQLite is the source of truth; a one-way bridge mirrors a curated subset of state into HA entities so the data is usable from automations and Lovelace. An optional thin Lit card reads those entities for an at-a-glance dashboard widget.

**Primary target:** a wall-mounted 10" tablet (1280×800, touch-only, landscape). UI must also work on phone and desktop, but the tablet is the design anchor.

**Non-goals (v1):** reward catalogue, per-kid PIN, TTS, photo-proof, multi-household sync. See §7 for where each future hook plugs in.

---

## 1. File tree (confirmed, one deviation)

Working directory is `/Users/jasonpatton/ToDoChore/`. The prompt shows `family-chores/` as the tree root — since the user already set up `ToDoChore/` as the project directory, we treat **that** as root and collapse the `family-chores/` level. The add-on's `slug` is still `family_chores` per §9 of the spec.

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

---

## 5. Deviations from prompt

- **2026-04-21 — dropped `map: [- type: share]` from `config.yaml`.** The prompt's sample manifest declared `share` access "for avatar uploads exposed to HA if desired." Avatars are served by our own FastAPI under `/api/avatars/...`, so there's no user-facing reason to make them visible at `/share`. Dropping this shrinks the add-on's permission surface. If a real need appears (e.g. using an avatar in HA notification attachments), re-add.
- **2026-04-21 — added `tini` as ENTRYPOINT.** The prompt said "no s6 needed for single process," which is true — tini isn't s6, it's a ~100KB init to reap zombies and forward signals so `docker stop` / add-on stop doesn't take 10 s to SIGKILL. Common pattern for single-process containers.
- **2026-04-21 — added `startup: application` and `boot: auto` to `config.yaml`.** Not mentioned in the prompt but standard for HA add-ons that depend on HA Core being up. `application` defers start until HA Core is ready, matching our reconcile-on-startup behaviour.
- **2026-04-21 — added `services/` directory alongside `core/`.** The prompt's file tree lists `core/` for "pure domain logic" but routes DB-backed orchestration (mark overdue, generate instances, recompute stats) through the scheduler. Putting async-session-using code under `services/` keeps `core/` genuinely pure (no SQLAlchemy imports) and makes unit tests easy. Prompt tree was illustrative; no conflict with §10.
- **2026-04-21 — added `timezone` option to `config.yaml`.** Not in the prompt's manifest snippet; needed so the scheduler has a sensible tz before milestone 5's HA tz fetching lands. Optional string (`str?`); empty = fall back to UTC.
- **2026-04-21 — replaced `todo.family_chores_<slug>` with user-managed Local To-do entities.** Rooted in the add-on-vs-integration constraint (see §4 #45). User-facing impact documented in INSTALL.md. Changes `member.ha_todo_entity_id` nullable string to the schema.

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
5. ☑ HA bridge — this milestone
6. ☐ SPA skeleton
7. ☐ SPA polish + card
8. ☐ Tests + CI

Stop and summarize for the human after each.

---

## 10. Changelog

- **2026-04-21** — Initial DECISIONS.md. File tree confirmed with one deviation (collapsed `family-chores/` wrapper since working dir is already `ToDoChore/`). All major tech choices recorded. Open questions queued against milestone 4. No code yet — next step is user sign-off on this plan, then milestone 1.
- **2026-04-21** — Milestone 1 complete (`d058db9`). Three manifest deviations logged in §5.
- **2026-04-21** — Milestone 2 complete. Added §4 entries #21–#28 covering DB conventions, PRAGMAs, Alembic integration, and the non-obvious WAL-backup pitfall we hit during integration testing. No new prompt deviations.
- **2026-04-21** — Milestone 3 complete. Added §4 entries #29–#33 (streak-as-of-yesterday, milestone transition semantics, catch-up rollover, scheduler skip flag, UTC fallback). Two new prompt-tree additions logged in §5 (`services/` dir, `timezone` option). Caught a real-world-feel bug while testing — today's PENDING instances breaking the streak on the same rollover that generated them — documented as #29.
- **2026-04-21** — Milestone 4 complete. Added §4 entries #34–#38 (parent JWT + refresh, error envelope with request IDs, WS notification-only protocol, inline instance generation on chore mutations, explicit MemberStats initialization). No new prompt deviations. 188 tests total (93 new): full HTTP coverage of every router, auth flow edge cases, WS hello/ping-pong/broadcast, global error shape, and service-level tests for undo-window expiry that need injected time.
- **2026-04-21** — Milestone 5 complete. Live probe against HA 2026.4.1 resolved §8 #1 and shaped the bridge design. Added §4 entries #39–#46 (async worker with debounce + backoff, env-based client discovery, deferred events, FC tag identity pattern, inline stats recompute, tz fallback chain, Local To-do provisioning flow, blocking startup reconcile). Two new §5 deviations (user-managed Local To-do entities, `ha_todo_entity_id` column). 218 tests total (30 new): HTTP-level `HAClient` via `httpx.MockTransport`, bridge worker behaviour with a `FakeHAClient` (coalesce, backlog cap, todo create/update flow), reconciler convergence paths (create / update / delete orphans / record UID-from-match), full end-to-end via a monkey-patched `make_client_from_env` showing a completion drives the right set of HA calls and event-retry on `HAUnavailableError`.
