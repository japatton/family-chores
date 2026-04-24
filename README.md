# Family Chores — Home Assistant Add-on

Family chore tracking and rewards for Home Assistant. Runs as a single
Supervisor-managed add-on with a web UI served through HA Ingress, plus an
optional Lovelace card for dashboard widgets.

> **Status:** under active construction. See [`DECISIONS.md`](DECISIONS.md) for
> the current architecture and [`CHANGELOG.md`](CHANGELOG.md) for milestone
> progress.

## Why

Chore apps that live outside HA force families to juggle another service,
another login, and another set of notifications. This add-on keeps everything
inside HA's trust boundary and publishes chore state as regular entities so you
can automate ("if Alice's streak breaks, blink the hall light"), display on any
dashboard, or expose through Voice.

## How it works at a glance

- **SQLite** inside the add-on is the source of truth for members, chores,
  and completions.
- The add-on **mirrors** per-member points, streaks, and chore items into HA
  entities (`sensor.family_chores_*`, `todo.family_chores_*`) via the
  Supervisor-proxied REST API. This is a one-way write; we never read state
  from HA to make decisions.
- The Ingress UI is a React SPA tuned for a **wall-mounted 10" tablet**:
  large tap targets, per-member color themes, confetti on completion.
- A lightweight **Lovelace card** ships separately for users who want a
  chore widget on a main dashboard; it reads the mirrored entities only.

See [`DECISIONS.md`](DECISIONS.md) §2 for the full data-flow diagram.

## Screenshots

> Captured from a synthetic dev install (no real family data). The
> Home-Assistant-disconnected banner that normally sits at the top in
> dev mode is hidden here for clarity.

<p align="center">
  <img src="docs/screenshots/today-desktop.png" alt="Today view — three member tiles (Alice 100%, Bob 33%, Carol 50%) with progress rings, weekly point totals, and current streaks" width="100%">
</p>

The **Today view** is the landing page on the wall-mounted tablet: one
tile per family member, a fluid-typography progress ring, and the
weekly + lifetime point totals. The greeting up top is contextual
("Good morning" / "Up late?"). Tap a tile to drop into that kid's
chore list.

<table>
<tr>
<td width="50%">
<img src="docs/screenshots/member-carol.png" alt="Carol's chore list — three big chore cards (brush teeth ✓ done, make bed pending, practice piano pending) with member-color theming">
<br>
<sub><b>Member view (kid)</b> — one-tap completion, 72px minimum tap
targets, faded-green cards for already-done chores. Each member's
screen is themed with their personal accent colour (Carol = green
fairy ✨). Slow background shift reduces image-retention on the
wall-mounted tablet.</sub>
</td>
<td width="50%">
<img src="docs/screenshots/member-alice-all-done.png" alt="Alice's celebration screen after finishing every chore for the day — confetti particles scattered around a 'You did it!' panel showing 20 points earned and current streak">
<br>
<sub><b>All-done celebration</b> — fires a fresh confetti burst when
the last chore of the day flips to done. Web Audio chime (A5 → C#6
two-note bell, no binary asset) plays alongside if the sound toggle is
on.</sub>
</td>
</tr>
<tr>
<td width="50%">
<img src="docs/screenshots/parent-approvals.png" alt="Parent mode → Approvals tab showing Bob's pending 'Make your bed' chore with Approve and Reject buttons">
<br>
<sub><b>Parent — approval queue</b> — members with
<code>requires_approval: true</code> mark chores as
<code>done_unapproved</code> on completion; points aren't awarded
until a parent approves. Reject sends it back to pending with an
optional reason recorded in the activity log.</sub>
</td>
<td width="50%">
<img src="docs/screenshots/parent-members.png" alt="Parent mode → Members tab listing Alice, Bob, Carol with avatars, points totals, streak counts, and per-row Approval / Adjust points / Delete actions">
<br>
<sub><b>Parent — manage family</b> — add/edit/remove members, toggle
the per-member approval flag, manually adjust points (with audit-log
trail), and link each member to a Local-Todo entity in HA for
two-way sync.</sub>
</td>
</tr>
<tr>
<td width="50%">
<img src="docs/screenshots/parent-chores.png" alt="Parent mode → Chores tab listing six chores (brush teeth, make bed, practice piano, take out trash, tidy your room, walk the dog) with their recurrence rules and assigned members">
<br>
<sub><b>Parent — chore catalog</b> — seven recurrence rules supported
(daily, weekdays, weekends, specific weekdays, every-N-days,
monthly-on-date, once). Creating or editing a chore regenerates
today's instances inline so a newly-added chore shows up
immediately — no waiting for the midnight rollover.</sub>
</td>
<td width="50%">
<img src="docs/screenshots/today-portrait.png" alt="The same Today view rendered at a phone-width viewport with member tiles stacked vertically" width="60%">
<br>
<sub><b>Phone / portrait viewport</b> — the same Today view scales
fluidly from a 32" wall-mounted portrait panel down to a phone, with
member tiles stacking vertically below ~640px. Typography uses
<code>clamp()</code>-based tokens; no discrete breakpoints.</sub>
</td>
</tr>
</table>

## Install

See [`INSTALL.md`](INSTALL.md) for step-by-step instructions (custom repository
or local add-ons folder).

## Threat model

Please read this before opening your HA to family or guests:

- The add-on runs **inside HA's trust boundary**. Anyone who can reach HA can
  reach this add-on. Use HA's own authentication as your real access control.
- The **parent PIN is a soft lock**, not a security boundary. It exists to
  stop a curious kid from hitting "delete member" from the tablet. Do not
  treat it as protection against a motivated attacker.
- Uploads are re-encoded through Pillow to strip metadata and enforce size
  limits.
- Logs never contain PIN hashes, JWTs, or the Supervisor token.

## Features (v1)

- Unlimited family members, each with avatar, color, and display mode.
- Seven recurrence rules (daily, weekdays, weekends, specific days, every N
  days, monthly-on-date, once).
- Points + streaks + weekly totals, with HA events fired on completion,
  approval, and streak milestones.
- Optional parent approval flow per member.
- Kid-friendly tablet UI with one-tap completion, 4-second undo, confetti.
- Parent admin view behind a PIN.

## Roadmap / out of scope for v1

- Redeemable reward catalog (points → real rewards).
- Per-kid PIN / profile lock.
- Voice / TTS announcements (you can wire these via automations today — the
  events are fired).
- Photo-proof of completion.
- Multi-household sync.

See [`DECISIONS.md`](DECISIONS.md) §7 for architectural hook points for each.

## Assets to replace before release

- [ ] `icon.png` — solid-color placeholder
- [ ] `logo.png` — solid-color placeholder

The completion chime is synthesised via Web Audio (two-note bell, A5 →
C#6), so no audio binary ships with the add-on.

## Development

See [`INSTALL.md`](INSTALL.md) "Local development" for running the backend
and frontend outside of HA.

## License

MIT.
