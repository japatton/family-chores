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
- [ ] `backend/src/family_chores/assets/chime.ogg` — completion chime (when added)

## Development

See [`INSTALL.md`](INSTALL.md) "Local development" for running the backend
and frontend outside of HA.

## License

MIT.
