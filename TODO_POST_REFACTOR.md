# Post-refactor TODOs

Items surfaced during the Phase 2 monorepo refactor that were deliberately
deferred to avoid scope creep. See `DECISIONS.md` §11 for refactor context.

When an item is picked up post-refactor, move it into its own issue / PR and
delete from this list. This file is the drift-catcher, not a long-term backlog.

## Drift candidates caught during refactor

### Multi-tenant follow-ups (surfaced in step 9)

Two model-level constraints assume single-tenant and need to be relaxed
before any real SaaS deployment can write data with non-NULL
`household_id`:

- **`AppConfig.key` is a single-column primary key.** Two households
  can't both store a row with the same `key` (`jwt_secret`,
  `parent_pin_hash`, etc.). Fix: an alembic migration that drops the
  `key`-only PK and adds a composite `(key, household_id)` PK (or a
  unique constraint). Step 9 documents this in
  `family_chores_api.security._get_app_config`'s docstring.

- **`Member.slug` has a global UNIQUE constraint.** Two households
  can't both have a member named `alice`. Fix: drop the global UNIQUE
  on `slug`, add a unique constraint on `(slug, household_id)`. Step
  9's integration test (`test_household_scoping.py`) currently works
  around this by using distinct slugs per household.

- **HABridge bypasses `scoped()` for two `ChoreInstance` queries**
  (`family_chores/src/family_chores_addon/ha/bridge.py` —
  `_publish_pending_approvals` at ~line 337, `_today_progress_pct` at
  ~line 317). Single-tenant addon mode is byte-identical because every
  row has `household_id = NULL`, but a multi-tenant deployment would
  count cross-household instances. Fix: thread `household_id` through
  `notify_*` and the flush loop, then add `scoped(...)` to both
  queries. Surfaced in the post-v0.3.0 code review as F-S005.

Neither change is on the Phase 2 refactor's roadmap (the SaaS isn't
real yet). They become blockers the moment a SaaS deployment writes
its first non-NULL-household row.

### Pre-existing cleanup

- `family_chores/tests/conftest.py` still has a
  `sys.path.insert(0, _SRC)` hack that predates the uv workspace
  install and is now redundant. Removing it is a trivial post-refactor
  cleanup; flagged-but-deferred in steps 3–6's outcome logs.
