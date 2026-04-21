# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
