# Family Chores — Home Assistant Add-on

Self-hosted family chore tracking and rewards for Home Assistant. This is the
add-on subdirectory; for the project landing page, screenshots, architecture
notes, and roadmap, see the [repo-root README](../README.md).

## What this add-on is

Family Chores runs as a Supervisor-managed add-on with an Ingress-served web
UI tuned for a wall-mounted tablet. It mirrors per-member chore state into
Home Assistant entities (`sensor.family_chores_*`, optional
`todo.family_chores_*` per-member sync) so you can automate against it,
display it on any dashboard, or hook it into Voice — without sending any
data outside your Home Assistant install.

## Features

- **Unlimited family members** with avatars, colour themes, and an optional
  per-member parent-approval mode.
- **Seven recurrence rules** — daily, weekdays, weekends, specific weekdays,
  every-N-days (with anchor), monthly-on-date, one-off. DST-safe.
- **Points + streaks + weekly totals**, with HA events fired on completion,
  approval, and streak milestones.
- **Kid-friendly tablet UI** — one-tap completion, 72px minimum tap targets,
  4-second undo toast, confetti + chime on completion, per-member colour
  themes, fluid typography from phones to a 32" portrait panel.
- **Parent mode behind a PIN** with approvals queue, chore catalogue, member
  management, manual point adjustments, and full activity log.
- **HA entity mirror** — `sensor.family_chores_<member>_{points,streak,today_progress}`,
  `sensor.family_chores_pending_approvals`, optional Local-Todo sync per
  member.
- **Optional Lovelace card** for dashboard widgets — see
  [`../lovelace-card/`](../lovelace-card/README.md).

## Install

In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories →**
add `https://github.com/japatton/family-chores` and install **Family Chores**.

Full step-by-step instructions, including a local-`addons/`-folder install
for development, are in the repo-root [`INSTALL.md`](../INSTALL.md).

## Configuration

| Option | Default | Notes |
|---|---|---|
| `log_level` | `info` | Bump to `debug` when filing a bug report. |
| `week_starts_on` | `monday` | Affects the weekly points-reset boundary. |
| `sound_default` | `false` | Completion chime default for new browser sessions. |
| `timezone` | `""` | Optional IANA name. Empty = follow Home Assistant. |

For per-member HA Local-Todo setup, the entity catalogue, the event schema,
and troubleshooting FAQs, see [`DOCS.md`](DOCS.md).

## Threat model (summary)

- The add-on runs **inside HA's trust boundary**. Anyone who can reach Home
  Assistant can reach this add-on. Use HA's own authentication as your real
  access control.
- The **parent PIN is a soft lock**, not a security boundary — it stops a
  curious kid from hitting "delete member" from the tablet, not a motivated
  attacker.
- Avatar uploads are re-encoded through Pillow to strip metadata.
- Logs never contain PIN hashes, JWTs, or the Supervisor token.

Full threat model and private vulnerability reporting:
[`../SECURITY.md`](../SECURITY.md).

## Documentation

- [`DOCS.md`](DOCS.md) — entity catalogue, event schema, dashboard
  integration, backup + restore, troubleshooting FAQs.
- [`CHANGELOG.md`](CHANGELOG.md) — per-release notes.
- [`../INSTALL.md`](../INSTALL.md) — installation step-by-step.
- [`../README.md`](../README.md) — project landing page with screenshots and
  architecture summary.
- [`../docs/architecture.md`](../docs/architecture.md) — monorepo layout and
  dependency direction.
- [`../docs/roadmap.md`](../docs/roadmap.md) — what's planned, what's on the
  radar, what's out of scope.

## Contributing

Issues and pull requests welcome — start with
[`../CONTRIBUTING.md`](../CONTRIBUTING.md). Security reports go through
[`../SECURITY.md`](../SECURITY.md), not public issues.

## License

[MIT](../LICENSE) © 2026 Jason Patton
