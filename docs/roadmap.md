# Roadmap

Family Chores is a personal project with a narrow scope — a household chore board for a wall-mounted tablet, self-hosted via Home Assistant. This document lists what's planned, what's on the radar, and what's explicitly out of scope.

New feature requests get triaged against this document. If you're thinking of opening one, read the "Out of scope" section first — it'll save us both time.

## Landed

The last few notable releases. For the full list, see [`family_chores/CHANGELOG.md`](../family_chores/CHANGELOG.md).

- **v0.5.0 (2026-05-01)** — calendar integration. Family Chores now
  reads HA `calendar.*` entities and surfaces today's events on each
  member's tile (with prep chips like 🥾 cleats, 💧 water bottle
  auto-extracted from event descriptions), shows a "Today's events"
  panel inside the kid view, and adds a Parent → Calendar tab with a
  monthly grid + per-member and household-shared mapping settings.
  Under the hood, the work introduced two provider Protocols
  (`CalendarProvider`, `TodoProvider`) that decouple the addon from
  HA-specific code, laying the groundwork for a non-HA standalone
  deployment without rewriting the bridge. See [DECISIONS §14](../DECISIONS.md)
  and [`docs/calendar.md`](calendar.md).
- **v0.4.0 (2026-04-26)** — per-kid PIN profile lock + redeemable
  reward catalogue + UX polish sweep. Kids unlock their own view
  with a 4-digit PIN (soft lock, not a security boundary); parents
  define a points-redeemable rewards list with an approve/deny
  queue. Plus the F-U001–F-U005 UX fixes from a children's-software
  expert sweep.
- **v0.3.1 (2026-04-25)** — chore suggestions. Bundled library of
  46 age-appropriate chore templates seed into the Add Chore form's
  new "💡 Browse suggestions" panel; tap a template to pre-fill every
  field. New chores default to saving themselves back into the library
  for next time. See [DECISIONS §13](../DECISIONS.md).
- **v0.2.4 (2026-04-24)** — clean re-cut after v0.2.2 + v0.2.3 tag
  mishaps. Manifest version field wasn't bumped at v0.2.2/v0.2.3 tag
  time so HA Supervisor never offered them; v0.2.4 ships the polish
  documentation + the new icon/logo PNGs end-to-end.
- **v0.2.1 (2026-04-24)** — clean re-cut of 0.2.0 with correct image tagging. The v0.2.0 git tag had preceded the `image:` field fix, so Supervisor couldn't find the `0.2.0` tag on GHCR; 0.2.1 is byte-identical in behaviour, correctly tagged end-to-end.
- **v0.2.0 (2026-04-23)** — internal monorepo refactor. No user-facing changes; HA Supervisor now pulls pre-built images from GHCR instead of building locally. See [`docs/architecture.md`](architecture.md) for the resulting shape.
- **v0.1.0** — first publicly installable release: kid-friendly tablet UI, parent mode behind a PIN, seven recurrence rules, HA entity mirror + Local-Todo sync, Lovelace card, full test suite, CI/CD.

## Near-term — under active consideration

These might land in a 0.3.x or 0.4.x cycle. No promises, no ordering.

- **HACS custom-repository polish.** The Lovelace card already installs as a custom HACS repository (see [`lovelace-card/README.md`](../lovelace-card/README.md)). Tidying up the `info.md`, version pinning, and the HACS manifest so the install feels first-class is low-lift.
- **Per-calendar color picker.** Today every event chip in the monthly grid shares the brand color. Letting parents pin a color per `calendar.*` entity (and surfacing it on the chip strip + day cards) would make the family-shared vs. per-member distinction visually obvious.
- **HA entity-id autocomplete.** Today the Calendar settings is a type-and-add chip input. A "list available `calendar.*` entities from HA" dropdown would shave friction when the parent doesn't remember the entity id offhand.
- **Voice / TTS convenience templates.** Events already fire on completion, approval, and streak milestones — you can wire Sonos, TTS, or any HA automation against them today. What's missing is a few copy-paste-ready automation blueprints in the add-on docs.
- **Photo-proof of completion.** Upload a photo to demonstrate the chore was done. Pillow re-encoding is already in place for avatars; storage tier (blob in DB vs. HA media) is the open design question.

## Longer-term — on the radar

Bigger shapes that would meaningfully change the project. Not committed to, not timelined.

- **Blueprint library + example dashboards.** A curated set of HA blueprints (chore-streak-broken → light pulse, approval-pending → phone nudge) and a few example Lovelace dashboards that go beyond the single card.
- **Export / import of chore catalogue.** YAML or JSON round-trip so families can share starter-pack chore lists.
- **HACS default-list submission.** This is a submission process, not a code change, and involves meeting HACS's published criteria (code quality, maintenance cadence, documentation). Currently blocked on maintenance-cadence confidence; revisit after a few release cycles.
- **Standalone (non-HA) deployment target.** Tier 2 of the calendar/todo decoupling roadmap (see [DECISIONS §14](../DECISIONS.md)). The provider Protocols introduced in v0.5.0 make this possible without rewriting the bridge — what's missing is a CalDAV / Google Calendar provider implementation and an `apps/standalone/` composition root. Open question: how heavy is the lift to get the addon's lifespan + auth shape working without HA Ingress?

## Explicitly out of scope

These are either against the grain of the project or scope expansions big enough that they deserve to be their own thing rather than a feature of this one.

- **Multi-household on the add-on.** The code supports `household_id` scoping at the data layer (see [`docs/architecture.md`](architecture.md#tenancy)), but the add-on deliberately doesn't expose it — one add-on instance = one household. Productising a multi-household deployment target is what `apps/saas-backend/` exists to show the *shape* of; turning that into a shipped product is out of scope for this repository.
- **Mobile apps.** The SPA is responsive and works on a phone in a browser. A native iOS/Android app is a different project.
- **Cloud sync or SaaS hosting.** Same reason as multi-household — the add-on is deliberately self-hosted. `apps/saas-backend/` is a scaffold, not a roadmap commitment.
- **Payment integration / allowance in dollars.** Explicitly non-goal. Points are abstract by design; converting them to real money adds regulatory surface (KYC, dispute handling, fraud) that makes no sense for a personal project.
- **Gamification beyond the current model.** Levels, achievements, badges, leaderboards. The current points + streak model is deliberately minimal; a full gamification system is a different product.
- **Integrations with third-party chore apps.** Not opposed in principle, but there's no standard format and writing bespoke integrations each time has a bad cost-to-benefit ratio.

## Where requests go

- **Feature requests** — [open a GitHub issue](https://github.com/japatton/family-chores/issues/new?template=feature_request.yml) using the feature-request template. Lead with the parenting or household workflow that's broken or missing.
- **Usage questions** that might turn into feature requests — [GitHub Discussions](https://github.com/japatton/family-chores/discussions) is the right forum.
- **Security reports** — see [`SECURITY.md`](../SECURITY.md). **Not** a public issue.
