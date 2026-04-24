## What

Brief description of the change. One sentence is often enough.

## Why

The problem this solves, or the behaviour it enables. If linked to an issue, `Closes #NNN`.

## Test plan

- [ ] `./scripts/lint.sh` passes locally (runs every CI gate in one command)
- [ ] Manual verification: _describe what you clicked, typed, and observed_

## Checklist

- [ ] One concern per PR (don't bundle an unrelated refactor)
- [ ] If architectural (new package, new dependency direction, cross-cutting refactor): appended a dated entry to [`DECISIONS.md`](../DECISIONS.md)
- [ ] If user-visible (new feature, behaviour change, removed feature): added a `[Unreleased]` entry to [`family_chores/CHANGELOG.md`](../family_chores/CHANGELOG.md)
- [ ] If UI changed: attached a screenshot or short clip
- [ ] Did **not** bump `family_chores/config.yaml` `version:` (release tags are cut separately by the maintainer)
