# Family Chores

Track family chores, award points and streaks, and surface chore state as
Home Assistant entities you can use in automations and dashboards.

## First-run setup

1. Open the add-on's Web UI (the "Open Web UI" button, or the sidebar panel
   labelled **Family Chores**).
2. You'll be prompted to set a **parent PIN**. This is a soft lock that
   prevents kids from hitting admin actions from the tablet — it is not a
   security boundary. Use HA's own authentication for real access control.
3. Add family members, then add chores and assign them.

## Configuration

| Option | Default | Description |
|---|---|---|
| `log_level` | `info` | One of `debug`, `info`, `warning`, `error`. |
| `week_starts_on` | `monday` | Week-boundary day for `points_this_week`. `monday` or `sunday`. |
| `sound_default` | `false` | Whether the completion chime is on by default for new browser sessions. |

## Entities published by the add-on

Entity names use the member's slug. The add-on never reads these entities —
they are a one-way mirror of its internal database.

- `sensor.family_chores_<slug>_points` — state = lifetime points. Attributes:
  `points_this_week`, `streak`, `today_progress_pct`, `member_id`.
- `sensor.family_chores_<slug>_streak` — state = current streak in days.
- `sensor.family_chores_pending_approvals` — state = count across all members.

### Todo / calendar

Per-member `todo.*` entities must be **user-created** via the Local To-do
integration (the add-on isn't a HA integration and can't create entities).
See `INSTALL.md` "HA To-do Setup". Once you map a member to their Local
To-do entity, Family Chores manages items with `[FC#<id>]` prefixes on
that list; HA surfaces them on its calendar automatically.

## Events fired

| Event | Payload |
|---|---|
| `family_chores_completed` | `member_id`, `chore_id`, `instance_id`, `points` |
| `family_chores_approved` | same as above |
| `family_chores_streak_milestone` | `member_id`, `streak_days` |

Wire these to `tts.*`, lights, or notifications as you see fit.

## Troubleshooting

- **Add-on won't start:** check the log for `Integrity check failed` —
  a corrupt database is auto-restored from `/data/family_chores.db.bak`
  if one exists; otherwise an empty DB is initialised and the UI shows a
  banner.
- **Entities not updating:** the add-on keeps a retry queue for HA REST
  calls. Check the log for `ha.sync` entries. The periodic reconciler
  runs every 15 minutes as a safety net.
- **Ingress panel blank:** the SPA falls back to cached data if the
  WebSocket drops. A "reconnecting…" pill is shown until it recovers.

## Support

File issues with the add-on log attached. Do not share logs containing any
`/data/options.json` secrets.
