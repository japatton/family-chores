# family-chores-saas

Placeholder for the SaaS deployment target. **Implementation in Phase 3.**

This scaffold exists so the monorepo workspace plumbing can be built and
tested without waiting on SaaS business logic. The shared `packages/core`,
`packages/db`, and `packages/api` are where all the real work happens;
this directory is just the composition root for a future cloud deployment.

See [`DECISIONS.md`](../../DECISIONS.md) §11 for refactor context.
