# Contributing

Family Chores is a personal project, built and maintained by one person on evenings and weekends. Contributions are welcome but I triage on a relaxed cadence — usually weekly. If you open an issue or PR and don't hear back for a week, a polite nudge is fine.

If you're thinking about a structural change (new package, new deployment target, schema migration, cross-cutting refactor), please read [`DECISIONS.md`](DECISIONS.md) and [`docs/architecture.md`](docs/architecture.md) first. The packages → apps dependency direction is enforced in CI by `tests/test_dependency_arrows.py` and won't bend; better to know before you start.

## Reporting bugs and requesting features

- **Bugs:** open an issue with the bug-report template. The template asks for HA version, add-on version, install method, reproduction steps, expected vs actual, and a log excerpt — all of those make the difference between a triage and a fix.
- **Features:** open an issue with the feature-request template. Lead with the parenting workflow that's broken or missing; the implementation can be discussed after we agree the problem is real.
- **Security issues:** see [`SECURITY.md`](SECURITY.md). Don't open public issues for security problems.
- **How-to questions** (configuration, dashboard setup, automation examples): the [add-on documentation](family_chores/DOCS.md) is the first stop, and GitHub Discussions is appropriate for anything not covered there.

## Development setup

You need:

- Python 3.12+ via [uv](https://docs.astral.sh/uv/) (`brew install uv` or follow the docs).
- Node 22 via [corepack](https://nodejs.org/api/corepack.html) (ships with Node 22) so `pnpm` is available — `corepack enable && corepack prepare pnpm@9.15.0 --activate`.
- Optional: Docker, only if you want to build the add-on image locally. CI builds it on every PR.

From a fresh clone:

```sh
# Install all workspace deps (Python + Node).
uv sync --all-packages --extra dev
pnpm install --frozen-lockfile
```

To run the backend + Vite dev server locally without HA:

```sh
# Terminal 1 — backend on http://localhost:8099
./scripts/dev_backend.sh

# Terminal 2 — Vite dev server on http://localhost:5173 (proxies /api → :8099)
./scripts/dev_frontend.sh
```

The dev backend uses a `NoOpBridge` (no HA connection required). For the full HA-connected experience, set `HA_URL` and `HA_TOKEN` before running `dev_backend.sh`.

## Running tests

The test suite is split per workspace member. From the repo root:

```sh
# Everything CI runs, in one command (~15s).
./scripts/lint.sh

# Or per-package:
uv run pytest packages/core/tests        # 57 tests, pure domain logic
uv run pytest packages/db/tests          # 37 tests, ORM + Alembic + scoped helper
uv run pytest packages/api/tests         #  2 tests, FakeAuthStrategy fixture smoke
uv run pytest family_chores/tests        # 147 tests, addon integration
uv run pytest apps/saas-backend/tests    # 12 tests, SaaS scaffold smoke
uv run pytest tests                      # 81 tests, architecture (dep-arrows + packages-clean)

# Frontend:
pnpm --filter family-chores-frontend test    # 26 tests, vitest
pnpm --filter family-chores-web test         #  2 tests, vitest
pnpm --filter family-chores-card typecheck   # type-only (no test runner)
```

Total: 364 passing tests across all workspaces. Adding code? Add tests. Changing behaviour? Update the affected test.

## Branch and commit conventions

- **Branch off `main`.** Name branches descriptively (`fix-undo-toast-flicker`, `feat-monthly-points-cap`).
- **Commits use [Conventional Commits](https://www.conventionalcommits.org/).** Examples in `git log` show the style: `fix(addon): ...`, `feat(api): ...`, `docs: ...`, `refactor(db): ...`, `chore(release): ...`. The type drives the changelog.
- **One concern per PR.** A PR that fixes one bug, adds one test, and refactors three unrelated files is three PRs.
- **Don't bump `family_chores/config.yaml` `version:` in your PR.** Releases are tagged separately by the maintainer; version bumps happen at tag time.

## Pull request expectations

The PR template has a short checklist. The substantive ones:

- Tests pass locally (`./scripts/lint.sh` exits 0).
- If your change is architectural (new package boundary, new dep direction, new abstraction), append a dated entry under the appropriate section of `DECISIONS.md` explaining what changed and why. Future contributors read DECISIONS to understand the system; an undocumented refactor is a hidden trap.
- If your change is user-visible (new feature, behaviour change, removed feature), add a `[Unreleased]` entry to `family_chores/CHANGELOG.md`. Don't invent a version number; the maintainer assigns it at tag time.
- If your change touches the UI, attach a screenshot or short clip in the PR description. The README's screenshots are real; we'd like to keep them current.
- If you touched any code path that the architecture tests cover (`tests/test_dependency_arrows.py`, `tests/test_packages_clean.py`), they will fail in CI before review starts. Run them locally first.

## What this project isn't

- Not accepting architectural rewrites that haven't been discussed in an issue first. The current shape is the result of two phases of refactoring documented in DECISIONS; please don't propose a third without a conversation.
- Not accepting cosmetic-only PRs (whitespace, file reorderings, comment polish). They generate review overhead without changing behaviour.
- Not currently building toward HACS default-list submission, multi-household, or mobile apps. See [`docs/roadmap.md`](docs/roadmap.md) for what is and isn't on the table.

## License

By contributing, you agree your contribution is licensed under the same MIT license as the project. See [`LICENSE`](LICENSE).
