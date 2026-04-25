# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] — 2026-04-25

Patch release addressing all six substantive findings from the
post-v0.3.0 code review (PR #10). All bug fixes; no new features.

### Fixed

- **Manual point adjustments now survive midnight rollover** (F-S001,
  HIGH). `recompute_stats_for_member` previously overwrote
  `MemberStats.points_total` with the chore-instance sum only,
  silently wiping any bonus a parent had awarded via
  `POST /api/members/{id}/points/adjust`. Migration 0005 adds
  `member_stats.bonus_points_total` (signed integer); recompute now
  folds it into the displayed total via
  `max(0, chore_sum + bonus_points_total)`. The outer `max(0, ...)`
  preserves the existing "displayed total never goes negative"
  invariant.
- **`today_progress_pct` HA sensor now uses the user's local date**
  (F-S002, MEDIUM). The bridge previously computed today against
  `utcnow().date()`, so for any non-UTC timezone the sensor reported
  yesterday's progress for the hours between local-midnight and
  UTC-midnight (US Pacific saw this for 8 hours every morning).
  HABridge now takes a `timezone_provider` callable matching the
  existing `IngressAuthStrategy.secret_provider` pattern; the addon
  lifespan passes a closure over `app.state.effective_timezone`.
- **Startup catch-up rollover failures now surface to the SPA**
  (F-S004, LOW). Previously logged-only; the kid's Today view stayed
  empty until something else triggered `generate_instances`. The
  exception summary lands on `app.state.rollover_warning`, surfaces
  in `/api/info`, and renders as a warning Banner above the main
  outlet. Fail-fast was rejected — degraded but running beats
  crash-looping on a transient error.

### Changed

- **`X-Remote-User` trust boundary documented in code** (F-X001,
  LOW). `IngressAuthStrategy._user_from()` picks up an 8-line comment
  explaining that the trust is network-boundary-enforced (Supervisor-
  managed addon network, Ingress is the only external path), not
  request-content-enforced. `family_chores/config.yaml` adds an
  explicit `network: {}` block so the port-exposure decision is
  auditable. **No runtime auth change** — the documented boundary
  was already the actual behaviour.

### Removed

- **Pillow + python-multipart dropped from runtime deps** (F-S003,
  LOW). Both were carried for an avatar-upload + re-encode flow that
  was specced in DOCS.md / README.md but never built. Trims ~5 MB of
  Pillow + alpine build-deps (`jpeg-dev`, `zlib-dev`, `libjpeg-turbo`,
  `zlib`) from every multi-arch image. `README.md`,
  `family_chores/README.md`, and `family_chores/DOCS.md` updated to
  match the URL-only reality of the `Member.avatar` field. Restoring
  the upload path means re-adding both deps + the build-deps in
  `family_chores/Dockerfile`; commits in PR #10 have the inline
  comments to make that easy.

### Internal

- `TODO_POST_REFACTOR.md` gains an entry for two HABridge queries
  that bypass `scoped()` (F-S005, LOW). Single-tenant addon mode is
  byte-identical because every row has `household_id = NULL`; this
  becomes a real gap only in a multi-tenant SaaS deployment.
- Migration 0005 (`add member_stats.bonus_points_total`) — round-trip
  + signed-value tests in `packages/db/tests/test_migration_0005.py`.

### Behaviour change worth knowing

The F-S001 fix slightly changes negative-adjustment semantics:

  - **Before**: parent deducts 100 from a 10-point member → displayed
    total drops to 0; the "extra" 90 points of deduction are
    discarded forever. Future chore points immediately raise the
    displayed total again.
  - **After**: same immediate display (still 0), but
    `bonus_points_total = -90` persists. The next 90 chore points the
    kid earns are absorbed by the deficit before the displayed total
    starts rising again.

This matches a real-world penalty semantic ("you owe 90 points"
actually means something) rather than the per-call clamp of the
original implementation. If the strict-clamp semantic is preferred,
a one-line clamp in `adjust_member_points` will restore it.

### Tests

- **+8 net new tests**, total goes from 509 → ~517 (the architecture-
  test parameterization shifts a bit with the new files):
  - `packages/db/tests/test_migration_0005.py` — 5 round-trip +
    signed-value cases.
  - `family_chores/tests/test_rollover.py` — 2 regression tests
    (positive bonus survives, negative bonus carries as persistent
    penalty across multiple rollovers).
  - `family_chores/tests/test_ha_bridge.py` — 1 regression test
    pinning `today_progress_pct` against a monkeypatched
    `utcnow` + Pacific tz.
- `./scripts/lint.sh` exits 0 across every workspace.

## [0.3.0] — 2026-04-25

### Added

- **Chore suggestions** (DECISIONS §13). The Add Chore form gains a
  "💡 Browse suggestions" affordance that opens an in-place panel
  showing a bundled library of **46 age-appropriate chore templates**
  spanning ages 3–12 across 11 categories (bedroom, bathroom, kitchen,
  laundry, pet care, outdoor, personal care, schoolwork, tidying,
  meals, other). Library content is grounded in American Academy of
  Pediatrics and AACAP age-appropriate-chore guidance. Search the
  list by name, filter by age, multi-select category chips, or scope
  to starter / custom only. Tapping a suggestion pre-fills name, icon,
  points, recurrence rule + config, and description in one click —
  parent then edits anything they want and saves normally.
- **Save-as-suggestion checkbox** below the Add chore button,
  **default checked**. Any new chore is saved back into the library
  by default so it's a one-tap pull next time. If the name dedups
  to an existing suggestion (starter or custom), the chore links to
  the existing one silently — no duplicates. A subtle "Saved 'X' as
  a suggestion for next time" status appears for 4 seconds after
  saves that produced a brand-new template.
- **Manage Suggestions view** reached from the "Manage my
  suggestions" link in the Browse panel. Lists custom suggestions
  with Edit / Delete; lists starter suggestions in a collapsed
  section with a Hide button (starter names are immutable; other
  fields editable). A quiet "Reset starter suggestions" link at the
  bottom restores any starters the parent had hidden.
- **First-run "✨ New" badge** beside the Browse suggestions button.
  One-shot per device, persisted in browser localStorage; disappears
  on first tap and never reappears.
- **Six new HTTP endpoints** under `/api/suggestions/` for
  programmatic access (list with filters, get, create custom, patch,
  delete with starter-suppression handling, reset). All parent-required.

### Changed

- `POST /api/chores` response shape extended with `template_id`
  (informational — the suggestion this chore was spawned from, if
  any) and `template_created` (boolean — true when this POST also
  added a new suggestion). `GET` and `PATCH` /api/chores responses
  also gain `template_id`. Backward compatible — clients that
  ignore the new fields are unaffected.
- `POST /api/chores` request body accepts two new optional fields:
  `template_id` (records source suggestion, validated against the
  current household) and `save_as_suggestion` (default `true`,
  drives the auto-save-to-library behavior).

### Migration

- New schema migration `0004_add_chore_templates`. Adds:
    `chore_template` table (UUID PK, household_id, name +
    name_normalized for dedup, icon, category, age_min/max,
    points_suggested, default_recurrence_type + config, description,
    source enum {starter, custom}, starter_key, timestamps; UNIQUE
    on (household_id, name_normalized) and (household_id, starter_key);
    composite index on (household_id, category)).
    `household_starter_suppression` table (composite PK on
    (household_id, starter_key) + suppressed_at).
    Two new columns on `chores`: `template_id` (nullable FK ON
    DELETE SET NULL) and `ephemeral` (BOOLEAN NOT NULL DEFAULT
    FALSE).
  Existing chore rows pick up `template_id=NULL`, `ephemeral=FALSE`
  on upgrade — no data backfill needed.
- The first add-on boot after upgrade **seeds 46 starter
  suggestions** into the database (idempotent — re-running is a
  no-op). Future library upgrades only seed new entries; existing
  rows are never overwritten so parent customizations survive.

### Privacy / HA

- **No new HA entities, events, or sensors.** Templates are a
  parent-side authoring convenience, not active state. Verified by
  three defensive tests in
  `family_chores/tests/test_template_no_ha_sync.py` that pin the
  contract structurally (the reconciler's SQL is asserted to never
  reference the chore_template or suppression tables).

### Tests

- **+145 tests** across the workspace, total goes from 364 → 509.
  Breakdown by suite:
  - `packages/core/tests` — starter library validation (26) +
    `normalize_chore_name` (19) = +45 → 102 total
  - `packages/db/tests` — migration 0004 round-trip + constraint
    enforcement (15) = +15 → 52 total
  - `family_chores/tests` — seeder integration (12) + suggestions
    HTTP (24) + chores POST extension (8) + HA-sync defensive (3)
    = +47 → 194 total
  - `family_chores/frontend` — BrowseSuggestionsPanel (9) +
    ManageSuggestionsView (10) + useFirstRunBadge (5) = +24 → 50 total
  - `tests/` (architecture) — parameterized dep-arrow + packages-clean
    checks pick up the new files = +14 → 95 total
  All green via `./scripts/lint.sh` (ruff + mypy + pytest + eslint +
  tsc + vitest across every workspace).

## [0.2.4] — 2026-04-24

### Added

- **Public-release polish documentation** (originally intended for
  v0.2.2). New governance files at the repo root: `LICENSE` (MIT),
  `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`,
  `.github/ISSUE_TEMPLATE/` (bug + feature request forms + config),
  and `.github/PULL_REQUEST_TEMPLATE.md`. Repo-root `README.md`
  rewritten as a public landing page with badges, screenshots, and a
  documentation map. New `docs/architecture.md` (monorepo layout,
  package → app dependency arrow, AuthStrategy protocol,
  household_id tenancy, data flow, testing topology, release
  topology) and `docs/roadmap.md` (landed, near-term, longer-term,
  explicitly out of scope). Add-on directory gains a store-facing
  `family_chores/README.md` (90 lines). Lovelace card picks up
  `hacs.json`, `info.md`, `CHANGELOG.md`, and a rewritten README
  with three documented install paths replacing the old "HACS
  support coming soon" stub. `family_chores/DOCS.md` expanded from
  83 → 253 lines with new Dashboard integration, Backup and restore,
  and Privacy sections, plus the troubleshooting FAQ doubled from 3
  to 6. All documentation-only — no code or behaviour changes; full
  test suite stayed green at 364 tests.
- **Replaced placeholder `icon.png` and `logo.png`** (originally
  intended for v0.2.3). Teal (`#14B8A6`) rounded-square icon with a
  white checkmark; matching 250×100 wordmark logo with a dark-teal
  "Family Chores" mark to the right of the icon. Both generated
  programmatically via Pillow, both well under 3 KB.

### Fixed

- **Re-cut after v0.2.2 + v0.2.3 tag mishaps.** Both prior tags went
  out with `family_chores/config.yaml` `version:` still pinned at
  `0.2.1`, so HA Supervisor never offered them as updates — the GHCR
  images were built and pushed correctly at `:0.2.2` and `:0.2.3`,
  but Supervisor reads the manifest's `version:` field to decide
  whether an update exists, and that field never moved. Same
  root-cause family as the v0.2.0 → v0.2.1 fix below: tag-time
  version-bump discipline. v0.2.4 is the clean re-cut, with the
  manifest correctly bumped end-to-end. The v0.2.2 and v0.2.3
  GitHub Releases are kept (force-deleting tags invites stale-cache
  trouble) but flagged as broken in their release notes — install
  v0.2.4 directly.

## [0.2.1] — 2026-04-24

### Fixed

- **`config.yaml` `image:` field + `release.yml` v-strip arrived in
  v0.2.0 but the `v0.2.0` git tag itself was pushed against the
  pre-fix commit, so the GHCR image was published as `:v0.2.0` while
  HA Supervisor expected `:0.2.0`. Re-tagging would force-push and
  invite stale-cache trouble; v0.2.1 is a clean re-cut from the
  fixed `main` instead. No code change vs the intended v0.2.0 — same
  refactor, same behaviour, correct tagging end-to-end.

## [0.2.0] — 2026-04-23

### Changed

- **Internal restructure to a monorepo layout.** This release is a large
  internal refactor that splits the add-on's code into shared workspace
  packages (`packages/core`, `packages/db`, `packages/api`) plus a thin
  `family_chores/src/family_chores_addon/` composition root for the HA
  add-on itself. **No user-facing changes** — every UI behaviour, every
  HA event, every entity name is identical to the previous release.
- **HA Supervisor now pulls the add-on image from GHCR** instead of
  building locally. Required by the new monorepo layout: the Dockerfile
  references workspace packages above the addon directory, which
  Supervisor's local build (which uses the addon dir as Docker context)
  can't reach. The pre-built multi-arch images are pushed to
  `ghcr.io/japatton/family-chores-{arch}` by the release workflow. The
  normal HA Supervisor update flow now downloads + extracts the image
  in seconds (no compilation). Your data at `/data/family_chores.db`
  is preserved because the add-on **slug remains `family_chores`**.
  See `DECISIONS.md` §11 for the full refactor sequence.

### Added

- **Milestone 8 — tests + CI.** Backend now clean under `ruff check` +
  `mypy --strict` (two targeted ruff ignores for `RUF059`
  unused-unpacked-variable and `UP042` `(str, Enum)` style). Route
  handlers all carry proper `_parent: ParentClaim` annotations; fixed
  real type bugs (int-of-None in recurrence config validation, HA
  client lifespan param typed as `object`, `create_engine` arg). New
  frontend test suite: Vitest + happy-dom + @testing-library/react +
  userEvent; 25 unit tests covering the parent / UI Zustand stores,
  the `apiFetch` client (JSON + 204 + error-body parsing + bearer
  header + JSON body serialisation), PinPad digit entry + backspace +
  disabled, UndoToast render + undo-click, ProgressRing rounding +
  clamping + aria-label. ESLint flat-config + Prettier-compatible
  rules. `scripts/lint.sh` runs the full CI stack locally in one
  command.
  CI on every PR via `.github/workflows/ci.yml`: parallel backend
  (ruff/mypy/pytest), frontend (eslint/tsc/vitest/build + artefact
  upload), and card (typecheck + rollup + artefact upload) jobs.
  `.github/workflows/release.yml` runs on version tags: multi-arch
  image build (`linux/amd64`, `linux/arm64`, `linux/arm/v7`) via
  `docker/setup-qemu-action` + `docker/build-push-action@v6` pushes
  to GHCR; a fan-in `publish-release` job attaches the Lovelace-card
  JS to the GitHub release. **243 tests total** (218 backend + 25
  frontend), all green.
- **Milestone 7 — SPA polish + Lovelace card.** Completion chime
  synthesised via Web Audio (two-note A5 → C#6 bell, no binary asset),
  gated on the persisted `soundEnabled` flag and a 🔔/🔕 toggle in the
  shell header. Member-accent-coloured confetti burst on every `DONE`
  completion via `canvas-confetti`. New `CelebrationAllDone` screen
  replaces the plain "All done" text, firing a second confetti burst and
  showing today's earned points + current streak. A slow 90-second
  `background-position` shift on the body reduces image-retention on the
  32" wall display; respects `prefers-reduced-motion`. New
  `lovelace-card/` workspace builds a single-file (~26 KB minified) Lit
  card via Rollup; reads HA entities only, surfaces each family
  member's points / streak / today progress, and shows a "pending
  approvals" badge when non-zero. Ships a GUI editor
  (`family-chores-card-editor`) so users don't have to touch YAML.
  Install steps in `lovelace-card/README.md` and `DOCS.md`.
- **Milestone 6 — SPA skeleton.** React 18 + TypeScript + Vite + Tailwind
  CSS + TanStack Query + Zustand + React Router, all wired to the existing
  HTTP + WebSocket API. Three main views (Today, Member, Parent) with
  parent routes split into Approvals / Members / Chores / Activity tabs,
  each gated by a PIN flow (first-run set-and-confirm vs verify; sliding
  refresh on user activity via `/api/auth/refresh`). Per-member theming
  via a single `--accent` CSS variable fed from `member.color`. One-tap
  chore completion with a 4-second undo toast; "⏳ Waiting for parent"
  state for approval members. Fluid typography via `clamp()`-based
  Tailwind tokens so a single build scales from phones to the 32"
  portrait target; 72 px minimum tap targets throughout. WebSocket
  auto-reconnects with exponential backoff and invalidates the relevant
  TanStack Query keys on each event. App shell shows a "reconnecting…"
  pill when the WS drops and banners when HA is disconnected or the DB
  bootstrap restored from backup. Dockerfile gained a `frontend-build`
  stage on Node 22 that compiles the SPA into
  `backend/src/family_chores/static/`; that directory is git-ignored
  except `.gitkeep` so built artefacts don't pollute diffs. FastAPI's
  static-mount check now keys on `index.html` rather than "dir non-empty"
  so the `.gitkeep` doesn't trip false mounting. Dev scripts added:
  `scripts/dev_backend.sh`, `scripts/dev_frontend.sh`, `scripts/lint.sh`.
- **Milestone 5 — Home Assistant bridge.** Full one-way mirror of SQLite
  state into HA entities. `family_chores.ha.client` is an async httpx
  wrapper that auto-picks `SUPERVISOR_TOKEN` (add-on runtime) or
  `HA_URL`+`HA_TOKEN` (local dev); its `HAClientError` hierarchy lets the
  bridge distinguish transient from fatal failures. `family_chores.ha.bridge`
  is an async worker task that debounces bursts (500 ms) and batches three
  notification channels — dirty member sensors, global pending-approvals
  count, and per-instance todo sync — into one HA round-trip per tick.
  Event firing uses a backlog (cap 1000, drop-oldest) with
  `HAUnavailableError` re-queueing for transient blips.
  `family_chores.ha.reconcile` diffs HA todo items against open chore
  instances and creates / updates / deletes to converge, using a
  `[FC#<id>] <chore>` summary prefix to identify items we manage.
  Per-member todo sync is opt-in via a new
  `member.ha_todo_entity_id` column (nullable; requires a user-provisioned
  Local To-do entity — see `INSTALL.md`). Lifespan fetches HA's timezone
  at startup, runs one synchronous reconcile pass, and wires the 15-min
  scheduled reconciler + streak-milestone event firing into the existing
  midnight-rollover job. 30 new tests (218 total) covering the HTTP
  layer (`httpx.MockTransport`), bridge behaviour against a `FakeHAClient`,
  reconciler convergence, and a full end-to-end lifespan test where a
  completion drives the expected set of HA calls.
- **Milestone 4 — HTTP API + auth.** Six routers (`auth`, `members`,
  `chores`, `instances`, `admin`, `ws`) wired under `/api/...`. Argon2
  PIN hashing + HS256 parent JWTs (5-min TTL) with a `/api/auth/refresh`
  endpoint for sliding-window parity with the prompt's 5-min-inactivity
  spec. `MemberStats.adjust` for manual point corrections with 0-clamp.
  Per-instance state transitions (`complete` / `undo` / `approve` /
  `reject` / `skip`) with a 4-second server-side undo window, activity
  log entries for every mutation, and idempotent `generate_instances`
  calls after chore create/update so a newly-added chore surfaces in
  today's view immediately without waiting for midnight rollover.
  WebSocket `/api/ws` broadcasts `{type, *_id, state}` deltas on every
  mutation; clients refetch the affected resource. Global error envelope
  `{error, detail, request_id}` + `X-Request-ID` header on every
  response, wrapping `DomainError` subclasses, Pydantic validation, and
  500s uniformly. 93 new tests (188 total) cover every router's happy
  + auth-failure paths, WS hello/ping-pong/broadcast, service-level
  undo-window expiry, and the error envelope shape.
- **Milestone 3 — recurrence, instances, scheduler.** Pure `core/`
  modules for recurrence (all 7 rule types with DST-safe date-only math,
  month-end clamping, every-N-days anchor-aware modulo), streaks (with a
  bounded-lookback walk and milestone-transition detection), and
  week-anchor points-reset math. Async `services/` layer covers instance
  generation + idempotent overdue marking + stats recomputation + full
  rollover pipeline. APScheduler wires a midnight `CronTrigger` job
  (DST-safe via IANA tz) and a 15-min HA-reconcile interval (stub until
  milestone 5). FastAPI lifespan now runs a startup catch-up rollover
  (same pipeline, same idempotence) so a cold boot after a missed
  midnight produces a consistent DB before the first request lands.
  New `timezone` option added to `config.yaml` (`str?`) — empty falls
  back to UTC until milestone 5 fetches the real tz from HA.
  95 tests total (76 new): per-rule recurrence coverage including DST
  spring-forward + fall-back + leap-year Feb 29, streak edge cases
  (zero-days, partial-done days, `done_unapproved` behaviour, lookback
  cap, milestone regressions), async service tests for generation/
  overdue/rollover, scheduler job-config smoke tests, and a full-
  lifespan boot test that verifies the catch-up rollover + bootstrap
  reporting end-to-end.
- **Milestone 2 — persistence layer.** Full SQLAlchemy 2.x model set for
  members, chores, chore assignments, chore instances, member stats,
  activity log, and app config; Alembic baseline at revision `0001_initial`.
  Async engine factory applies `PRAGMA foreign_keys=ON` + WAL + NORMAL
  synchronous on every connection. FastAPI `lifespan` context runs the
  integrity-check → backup → migrate → recover flow on startup and stashes
  the engine + session factory on `app.state`. `/api/info` now reports the
  bootstrap action and any recovery banner. Backup step issues a WAL
  `TRUNCATE` checkpoint before copying, so the backup is a complete
  single-file snapshot even when most state lives in the `-wal` sidecar.
  19 pytest cases cover model constraints, cascades, JSON round-trip, and
  all four bootstrap paths (initialized / migrated / restored_backup /
  reset_corrupt).
- **Milestone 1 — add-on skeleton.** HA add-on manifest (`config.yaml`),
  multi-arch `build.yaml`, Dockerfile using the `base-python:3.12-alpine3.20`
  image, minimal FastAPI entrypoint exposing `/api/health` and `/api/info`,
  placeholder Ingress landing page, `.dockerignore`, `.gitignore`. The backend
  boots cleanly under `python -m family_chores` and serves the placeholder UI.
- **Pre-work.** `DECISIONS.md` (running design notes) and `PROMPT.md`
  (verbatim build spec).
