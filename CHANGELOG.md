# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
