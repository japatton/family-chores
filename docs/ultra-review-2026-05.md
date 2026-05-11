# Ultra-review consolidated report — 2026-05

Three-iteration multi-agent codebase review of `family-chores` at v0.5.0. **~150 distinct findings** + **35 product ideas** + **10 architectural redesigns** + **27 load-bearing patterns to preserve**, distilled into a prioritized 6-month roadmap.

The detailed register lives at `.ultra-review-state.md` (511 lines); this document is the executive summary + roadmap + preservation charter.

---

## How this review was conducted

Three iterations of parallel agent dispatch + deconflict, self-paced via `/loop`. Each iteration ran 5–8 agents concurrently, each agent doing deep file-level research before reporting structured findings. Cross-pollination + skeptical pass between iterations sharpened the register and dropped false positives.

| Iteration | Agents | New findings | Focus |
|-----------|--------|--------------|-------|
| 1 | 8 | 41 + 15 ideas | Broad sweep: architecture, DB, API/frontend, HA bridge, frontend UX, testing/CI, security, blue-sky ideas |
| 2 | 6 | ~80 + 5 architectural | Validate HIGH findings; concurrency deep dive; SaaS-readiness; performance; untouched corners (Lovelace, observability, docs, dev exp, release); cross-pollination matrix |
| 3 | 5 | sharpen + 23 UX + 10 ideas | Skeptical pass; MVP implementation plan; preservation charter; roadmap synthesis; parent + kid user-POV |

Quorum was reached when iter-3 stopped adding net-new architectural findings — the surface had been mapped exhaustively. Iter-3's contributions were sharpening (refuting/correcting earlier findings), implementation planning, and user-experience gaps that engineers don't surface on their own.

---

## Tier 1 — Critical correctness fixes (next minor: v0.6.0)

Bugs hitting users today. ~10 working days. Ship as one release.

| Bundle | Findings | User-visible symptom | Fix shape | Effort |
|--------|----------|----------------------|-----------|--------|
| **1.1 Calendar multi-day events** | D-1, D-3 | Multi-day events ("Spring Break", tournaments) silently disappear from days 2..N after first cache hit. Cache hit returns `[]` (stored empty list under the day), never re-fetches. | Cache rekey per Tier 2.3 fixes it permanently; hot-fix is "expand event over all covered days in cache fill" | 2 days |
| **1.2 Redemption tz drift** | D-2, R-1 | Non-UTC families (LA/NZ) see weekly redemption-cap misfires near Sunday midnight local (window-edge error 7-14h) | Convert `week_start` local→UTC once before any `requested_at` compare; remove `today=None` fallback in `redemption_service.py:203` | 1 day |
| **1.3 Bridge UID write-back loss** | H-2, R-2 | After transient HA outage, bridge **creates duplicate todos** for already-mirrored chores until 15-min reconciler heals them | Commit per-instance after each successful add inside `_flush_once`, not at end of loop | 2-3 days |
| **1.4 Reconciler ↔ bridge race** | H-6, C-4 | Newly-added HA todos can vanish seconds after creation when reconciler's "orphan" sweep happens mid-bridge-flush | Reconciler acquires `bridge._flush_lock`; proper fix is Tier 2.4 (move reconciler into bridge worker) | 2-3 days |
| **1.5 PIN rate-limit + lockout UI** | S-1, U-1, F-10 | 4-digit PIN brute force is ~7 min single-host (Argon2 default cost). UI gives kid no signal of server-side throttling. | `Depends(rate_limit("pin_verify", per_user_window))` + frontend surfaces `remaining_attempts` / `locked_until` from server | 4-5 days |

**Skeptical-pass corrections applied:**
- D-1's first-pass fix ("expand event over all days") would balloon a yearly birthday into 365 cached refs per member. Use Tier 2.3 cache rekey instead.
- C-6's symptom is *silent lost-update* (last writer wins on two-tab approve), not 500 SQLITE_BUSY (aiosqlite's busy_timeout waits). Use SQLAlchemy `version_id_col` on `Redemption` for optimistic locking.

---

## Tier 2 — High-leverage architectural moves (v0.7.0 → v0.9.0)

Five bundles. ~7 weeks cumulative. Cross-pollination matrix verified all five compose (no conflicts), with two enable-relationships.

| Bundle | Eliminates | Pre-conditions | Effort |
|--------|-----------|----------------|--------|
| **2.1 `family_chores_api.testing` subpackage** | A-5 (NoOpBridge dup), A-6/T-4 (FakeAuthStrategy dup), T-3 (migration test boilerplate), S2-1 (SaaS smoke gaps) | None — pure refactor. Move `FakeAuthStrategy` + `FakeHAClient` + `NoOpBridge` + new `make_test_app()` into `packages/api/src/family_chores_api/testing/`. Migrate `HAClientError`/`TodoItem` to `packages/api/services/todo` first (dependency-arrow constraint). | 1 week |
| **2.2 Durable HA event queue** | H-2, H-3, H-4, H-12, C-2, C-3, C-11 (seven findings collapse to one) | 2.1 (test harness). New `pending_ha_event` table + worker drains from DB instead of in-memory list. Route opt-in for atomic in-tx enqueue. | 2 weeks |
| **2.3 Cache rekey + bound** | D-1, D-3, D-5, R-3, R-4 | None (but ship after 1.1 hot-fix). Key by `(household_id, entity_id, window_start, window_end)` + `TTLCache(maxsize=512, ttl=60)`. Multi-day events trivially work because cached per-window. | 1 week |
| **2.4 Reconciler-in-worker** | H-5, H-6 (definitively), H-11, C-4 | 2.2 (queue makes this natural — reconcile becomes a queue producer). Move reconcile inside bridge worker drain cycle. | 1 week |
| **2.5 Typed pub/sub bus** | F-3, F-4, F-5, the dual-fanout problem; unblocks future SaaS push | 2.1 + 2.2. One `bus.publish(DomainEvent)`; WS, bridge, audit log, future SaaS-push are subscribers. **Requires DECISIONS §11 Q4 amendment** ("typed Event = zero benefit" was correct in 2026-04 with 1 subscriber; payoff materializes with 2+). | 2 weeks |

**Skeptical-pass clarification on N-1 (typed bus):** the original framing was "every mutation enqueues twice" — that's misleading. The bridge gets 3-4 `notify_*` calls + sometimes `enqueue_event`; WS gets 1 `broadcast`. Different shapes for different needs. The bus's value is **organizational + adding new sinks** (audit log, SaaS push, metrics), not deduplication. Severity HIGH-LEVERAGE remains correct.

---

## Tier 3 — User-facing feature wins (1–2 quarters)

5 picked from 35 ideas. Each justified over alternatives below.

### 3.1 — Approve from phone via HA Companion *(VERY HIGH ROI)*

> *"I'm at work. The kid finished piano practice. I tap 'Approve' on the notification. Done. I don't open the tablet, I don't open HA."*

The bridge already fires `family_chores_chore_completed` events with `member_id` and `instance_id`. Ship a blueprint in `family_chores/blueprints/`:
- Trigger: `family_chores_chore_completed` where `requires_approval == true`
- Action: `notify.mobile_app_*` with two `action:` buttons (FC_APPROVE / FC_REJECT)
- Second trigger: `mobile_app_notification_action_received` → `rest_command.fc_approve|fc_reject`
- New `POST /api/instances/{id}/approve` accepting an HA service-call signature (auth = Supervisor-bearer, no parent JWT required)

**Impact: HIGH** (eliminates #1 friction for parent-required-approval mode). **Effort: M** (~1 week). **Risk:** iOS Companion sometimes drops actions silently — document tablet fallback.

### 3.2 — Time-of-day buckets

> *"'Brush teeth' should appear morning AND evening. Today it's just 'today' — no way to express that without two chores."*

Add `chore.time_buckets: list[str]` (`["morning"]`, `["evening"]`, `["morning","evening"]`, `["anytime"]`), defaulting `["anytime"]`. One Alembic migration; existing chores get `["anytime"]` (no behavior change). Add `bucket: str` to instance (not multiply rows). MemberView splits today's chores into auto-collapsed sections (morning/anytime/evening), current-bucket auto-expanded by clock.

**Streak semantics:** completed = all `today`-bucket instances done (ignore future buckets until current). **Document in DECISIONS amendment.**

**Impact: HIGH.** **Effort: M** (1 wk backend + 1 wk frontend). **Risk:** streak math edge cases on bucket boundaries.

### 3.3 — Photo-proof on-device only

> *"He says he made his bed. He didn't. I want a photo."*

Per-chore opt-in `requires_photo: bool`. Kid view shows native `<input type="file" capture="environment">`. Backend stores `/data/proofs/<instance_id>.webp` (Pillow re-encode + 800px cap + EXIF strip). Adds `proof_path` to `chore_instance`. Parent approval queue shows thumbnail. Auto-purge after 30 days. **No HA mirror, no upload anywhere.**

Ship with a `StorageProtocol` from day one (`LocalDiskStorage` here; `S3Storage` is free-future-work for SaaS).

**Impact: HIGH for approval-mode households.** **Effort: M** (~1 week). **Risk:** disk quota (mitigate via 800px cap + 30-day purge + `du`-based ceiling).

### 3.4 — Mystery chore

> *"My 6-year-old asks 'what's the surprise today?' before I've finished my coffee."*

Single sealed card on kid view; tap reveals one random `mystery: true` chore from parent-curated pool. ~150 lines, no migration (reuses `chore.mystery: bool`). Survives the gamification ban because it's a **cue**, not levels/badges.

**Impact: HIGH for kid engagement.** **Effort: S** (3-4 days). **Risk:** novelty wears off in ~2 weeks; keep pool small + parent-curated.

### 3.5 — Reduced-motion + SR audit

> *"My kid has vestibular issues. The confetti makes him sick."*

Honor `prefers-reduced-motion` across `Confetti`, `Cowbell`, animated decorations; SR audit on ChoreCard, MemberTile, RedeemConfirmModal, MonthGrid (covers iter-1 U-2/U-3/U-4). Genuine accessibility hole.

**Impact: MEDIUM** (small affected population, acute when it hits). **Effort: S** (3-4 days). **Risk: none.**

**Rejected from Tier 3:**
- **N-4 sticker book** — visual complexity needs art assets (out of solo-maintainer wheelhouse); defer.
- **N-5 voice via HA assist** — blocked on HA assist intents API stability.
- **N-6 adaptive difficulty** — premature optimization for current household scale.
- **N-9 PWA + offline** — wall-mounted tablet is wired-power, wired-network.
- **N-13 yesterday review** — delightful but redundant with parent's at-a-glance points.

---

## Tier 4 — SaaS readiness (when business signal exists)

The iter-2 SaaS-readiness agent identified **16 pre-launch blockers**. Bundled into 5 themes; ~12 weeks cumulative. **Do not start without business signal.**

| Theme | Findings | Why bundled | Effort |
|-------|----------|-------------|--------|
| **4.1 Tenancy + Postgres** | T-1, T-2*, T-3, T-4, T-5, T-6, T-7, D-1...D-6 | 13 findings break the same way — SQLite NULL/global-unique semantics + naive UTC don't survive Postgres. **Precondition for all other SaaS work.** | 4 weeks |
| **4.2 Auth + cookies + CSRF** | A-1, A-2, A-3, A-4, S-new-A, CS-1, CS-2, S-5 | All cross-origin browser auth concerns; httpOnly cookies + CSRF tokens + JWKS verification land together | 2 weeks |
| **4.3 Multi-worker cache + jobs + WS** | C-1 (saas), C-2 (saas), W-1, W-2, W-3, J-1, J-2, R-1 | Single-process assumptions across cache, scheduler, WS fanout, rate-limit token buckets. All require Redis. | 3 weeks |
| **4.4 Observability** | O-1, O-2, O-3, O2-1, O2-2, O2-3 | `structlog` wiring + Prometheus + OTEL + Sentry + `/live` vs `/ready` split + slow-query hook | 1 week |
| **4.5 Privacy / GDPR** | P-1, P-2, P-3, P-4 | Delete-my-household + data-export + retention + PII scrub. **Must ship before any public launch.** | 2 weeks |

\* T-2 was downgraded by the skeptical pass: `scoped(None)` in Postgres-NOT-NULL returns zero rows (not silent leak). Defensive raise still recommended; severity LOW.

Sequence: 4.1 → (4.2 ‖ 4.3) → 4.4 → 4.5.

---

## Tier 5 — Nice-to-haves (someday/maybe)

- **All LOW findings** (~30 items across D-6/7/8/9/10, F-3/8/9, U-6/7/8/9/10, T-9/10, S-6/7/8/10, M2-2, X2-2, R2-2/3, C2-2/3): batch as quarterly cleanup PRs.
- **Deferred ideas:** N-1 (morning hello), N-4 (sticker book), N-5 (voice), N-6 (adaptive), N-8 (family meeting), N-9 (PWA), N-10 (i18n), N-11 (calendar `[chore: X]` auto-create), N-13 (yesterday review), N-14 (YAML export), U-new-A (`/tomorrow`), U-new-B (7-day list), U-new-C (themes).
- **Wildcards** WC-1...WC-5: revisit only on specific user pull.
- **Lovelace card** L2-1...L2-6: single "lovelace polish" PR when convenient.
- **Frontend codegen** F-new-A: schedule when sufficient OpenAPI drift event happens.
- **Topic SSE** F-new-B: near-trivial after 2.5 (typed bus); revisit then.

---

## Preservation charter — what NOT to change

Curated from iter-3's "what we got right" pass. Any refactor must protect these invariants.

### Architectural invariants

- **Dependency-arrow tests** (`tests/test_dependency_arrows.py`, `tests/test_packages_clean.py`) stay green; pre-merge blockers. They prevent silent re-coupling of `packages/` to a deployment target.
- **Provider Protocols** (`BridgeProtocol`, `CalendarProvider`, `TodoProvider`, `AuthStrategy`) are seams; never bypassed for "convenience." Routers never know about HA.
- **`scoped()` helper is mandatory** for new queries. No inline `col == None`; SQLAlchemy's NULL-equality trap stays covered.
- **`NoOpBridge` / `NoOpCalendarProvider`** stays the boot path under missing credentials. The addon must run without HA.

### Failure-handling invariants

- **Calendar fetch on `/api/today` stays best-effort** — never blocking chore render.
- **`CalendarProviderResult.unreachable: list[str]`** — per-entity error reporting, not all-or-nothing.
- **Reconciler stays as the periodic safety net** — even after durable queue (2.2) lands. Drift sources include user manual edits, not just lost events.

### Concurrency invariants

- **Events fire AFTER commit** — `_finalize_action` order is load-bearing (DECISIONS §4 #41).
- **`expire_on_commit=False`** stays (`packages/db/.../base.py:42`) — post-commit fanout depends on it.
- **Naive-UTC DB convention is uniform** — any aware-datetime/Postgres migration is **all-or-nothing**, never partial.
- **One canonical `family_chores_core.time.utcnow`** — never add `datetime.now(UTC)` to a router.
- **APScheduler config:** `coalesce=True, max_instances=1, misfire_grace_time=3600` on every cron job.

### UX invariants

- **`min-h-touch`** is the floor for any kid-facing interactive surface.
- **`prefers-reduced-motion`** gates every animation; new animations must opt in.
- **Ratio-based progress phrasing** (F-U002) — no raw numbers when ratios speak louder.
- **Neutral-warmth greetings** (F-U001) — UI strings carry no social weight or bedtime enforcement.

### Documentation invariants

- **DECISIONS.md completion subsections persist** after work ships — historical record, not spec.
- **Migration 0008 cascade-delete docstring stays** — hard-won SQLite `batch_alter_table` trap knowledge. Re-trip = silent data loss.
- **`HouseholdSettings` synthetic `id` PK + nullable `household_id` shape stays** — SQLAlchemy NULL-PK workaround. Copy this shape for any single-row-per-household table.

### Top-5 best DECISIONS entries (load-bearing)

1. **§4 #21 Naive-UTC DB convention** — uniformity is what makes the Postgres migration possible at all.
2. **§4 #41 Events fire AFTER commit, from the bridge worker** — prevents events for rolled-back transactions.
3. **§4 #40 NoOpBridge fallback** — Tier-2 standalone achievable because the seam already works.
4. **§4 #46 Reconciler as periodic safety net** — lets the bridge stay best-effort.
5. **§11 Q3 Secret injection (no module-level JWT secret)** — protects multi-deploy from "module-top env-read" anti-pattern.

### 5 patterns worth stealing

1. **`scoped(col, value)` helper** — 15-line predicate centralization; one finding-class protected.
2. **`CalendarProviderResult.unreachable: list[str]`** — per-entity error reporting alongside data.
3. **Two architecture pytest files** (~200 lines each) preventing multi-month re-coupling regressions.
4. **F-S001 `bonus_points_total` signed-delta column** alongside computed-from-logs total — recompute idempotence without losing parent adjustments.
5. **`FAMILY_CHORES_SKIP_SCHEDULER=1` env knob** — one lifespan toggle keeps APScheduler out of pytest's event loop.

---

## Anti-roadmap — explicitly NOT shipping

1. **Multi-language i18n (N-10).** Wait for first non-English-speaking user demand. Maintenance tail of unused translations.
2. **Voice-driven completion (N-5).** HA assist API is in flux. Revisit when stable.
3. **PWA install + offline (N-9).** Wall-mounted tablets are wired-power, wired-network. Near-zero offline value.
4. **SaaS work (Tier 4) without business signal.** 12 weeks of pure cost for a single-tenant addon.
5. **Anthropic-powered chore extraction (WC-1).** Conflicts with DECISIONS §1 (no inference dependencies in addon path).

---

## 6-month commit (5 releases, defended)

If only 5 things ship in the next 6 months, ship these.

### v0.6.0 — Critical correctness fixes (Tier 1)
*Defense:* Three of five (D-1, D-2, H-2) are silently corrupting user data **today**. Punting means existing users keep getting bitten. Single-week budget; no excuse.

### v0.7.0 — Testing pkg + HA Companion approve (Tier 2.1 + Tier 3.1)
*Defense:* 2.1 unblocks every later refactor with test confidence (invisible to users). 3.1 is the **highest parent-ROI feature in the entire register** (press-release-grade). Ship them paired — one invisible, one headline.

### v0.8.0 — Durable HA event queue + cache rekey (Tier 2.2 + 2.3)
*Defense:* Eliminates **11 findings** (H-2/3/4/12, C-2/3/11, D-1/3/5, R-3/4) in two correctness-grade architectural moves. After this ships, "the bridge is flaky" complaints stop.

### v0.9.0 — Time-of-day buckets + photo-proof + reduced-motion (Tier 3.2 + 3.3 + 3.5)
*Defense:* Three user-visible features in one cycle. Buckets answer the most-requested data-model gap. Photo-proof lands the `StorageProtocol` for free. Reduced-motion is the right thing to do.

### v0.10.0 — Reconciler-in-worker + typed bus + observability slice (Tier 2.4 + 2.5 + 4.4 light)
*Defense:* Ends the "ad-hoc fanout" era. Adds Prometheus + structlog so production is debuggable. Mystery chore (3.4) ships in the same release as a delight stocking-stuffer.

**Cumulative:** ~6 months elapsed at solo-maintainer pace, evenings + weekends + occasional focused Saturday.

---

## Critical correctness summary (the "must-fix" picture)

These are real bugs affecting users right now. They were validated against actual code in iter-2's HIGH-finding validation pass. Citations below.

- **D-1**: `packages/api/services/calendar/service.py:168-181` — multi-day events bucketed by `event.start.date()` only; days 2..N cached as `[]`.
- **D-2**: `packages/api/services/redemption_service.py:157-158, 203-204` + `routers/rewards.py:306` — `week_anchor` from `local_today(tz)` compared against naive-UTC `Redemption.requested_at`.
- **H-2**: `family_chores/.../ha/bridge.py:271-295, 415-420` — `_sync_instance_todo` writes `inst.ha_todo_uid` then later iteration's `HAClientError` rolls back the whole tx. Bridge actively creates duplicate todos on retry.
- **H-6**: `family_chores/.../ha/reconcile.py:102-119` vs `bridge.py:233` — reconciler opens own session, doesn't acquire `_flush_lock`; concurrent bridge add + reconciler orphan-delete = freshly-added todo vanishes.
- **S-1**: `packages/api/.../routers/auth.py:85-99`, `routers/members.py:293-311` — zero rate-limit middleware codebase-wide. Argon2 cost gives ~7-min 4-digit space crack.

All five are eliminated by the v0.6.0 release (Tier 1).

---

## Architectural moves summary (the "design payoff" picture)

These are the multi-finding-elimination architectural shifts iter-1+iter-2 surfaced and iter-3 cross-pollinated.

1. **`family_chores_api.testing` subpackage** — closes 5 findings; ~2 days; foundation for SaaS test harness.
2. **Durable HA event queue** (SQLite `pending_ha_event` table) — closes 7 findings; ~3-4 days; eliminates the in-memory-list class of bugs.
3. **Cache rekey** to `(household_id, entity_id, window_start, window_end)` — closes 5 findings; ~3 days; multi-day events trivially work because cached per-window.
4. **Reconciler-in-worker** — closes 4 findings; ~1 week; eliminates the bridge race entirely.
5. **Typed pub/sub bus** — closes 3 findings + unblocks SaaS push; ~2 weeks; requires DECISIONS §11 Q4 amendment.

The five compose; the cross-pollination matrix showed no conflicts and two enable-relationships (queue → reconciler-in-worker; testing pkg → everything's test story).

---

## Findings register reference

The full ~150-finding register lives at `.ultra-review-state.md`. This document references it but does not duplicate every cell. Conventions:
- **Severity ladder:** CRITICAL → HIGH → MED → LOW → INFO/NIT
- **Finding codes:** prefix indicates area (A=architecture, D=DB/services, F=API/frontend, H=HA bridge, U=UX, T=testing/CI, S=security, P=perf, N=new ideas, WC=wildcards, with `-new-X` for proposed redesigns).
- **Iter-3 sharpening** is folded into the relevant Tier 1/2 entries; the register file keeps the raw verdicts for audit.

---

## Process notes (for future reviews)

Things this loop did well, worth repeating:
- **Multi-agent parallelism** + **explicit deconflict** at iteration end — agents found genuinely different things; deconflict avoided "8 agents say the same thing N times".
- **State file persistence** between iterations — let agents in iter N read the register from iter N-1 and avoid re-discovering known findings.
- **Skeptical pass in iter 3** — caught the D-1 fix overreach (would balloon cache for 365-day events), refuted T-2 (no actual leak), and corrected C-6 symptom description. Without it, the roadmap would have shipped wrong fixes.
- **User-POV pass added late** — 23 UX findings engineers don't surface on their own. Should land EARLIER in future reviews (iter 2 instead of iter 3) so engineering decisions can react to user concerns.
- **Preservation charter** — counter-balance to criticism; documents what works so refactors don't accidentally regress good patterns.

Things to refine for next review:
- **User-POV agent earlier in the sequence.**
- **Track agent-finding overlap explicitly** — iter 2 sometimes re-discovered iter 1 findings under different codes; deconflict caught most but ate cycles.
- **Implementation plan agent in iter 2, not iter 3** — concrete code shapes would have informed iter-2 architectural proposals.

---

*Loop terminated 2026-05-01 — exhaustive coverage reached; further iteration would be diminishing returns. Total: 3 iterations × ~6 agents/iter ≈ 18 deep-research agent runs.*
