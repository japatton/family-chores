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

## Suggestions

The Add Chore form ships with a **library of 46 age-appropriate chore
suggestions** so you don't have to type out the common ones (make bed,
brush teeth, walk the dog, take out trash, etc.). Spans 11 categories
across ages 3 to 12+, grounded in American Academy of Pediatrics
guidance.

### Using a suggestion

1. Tap **💡 Browse suggestions** at the top of the Add Chore form.
2. Search by name, filter by age, or pick a category chip. The Source
   filter (hidden behind "Filter by source") lets you scope to your
   custom suggestions or the starter library only.
3. Tap a suggestion. The form pre-fills with its name, icon, points,
   recurrence rule, and description. Edit anything you want, assign
   it to one or more family members, and save normally.

The first time you open the Chores tab after install, a small "✨ New"
pill draws attention to the Browse suggestions button. It disappears
on first tap and never reappears.

### Saving a chore as a suggestion

The Add Chore form has a **💾 Save as a suggestion for later** checkbox
sitting next to the Save button, **default checked**. When checked, any
chore you save also lands in the suggestion library so the next time
you (or your kid's other parent) need that same chore, it's one tap
away. Uncheck the box for one-off chores you don't want to keep around.

If you save a chore whose name already matches an existing
suggestion (your own or a starter), no duplicate is created — the
chore simply links to the existing suggestion silently.

### Managing your suggestions

From the Browse Suggestions panel, tap **Manage my suggestions** to
get an editor:

- **Your suggestions** — custom suggestions you've created, with Edit
  and Delete buttons. Editing changes only the suggestion (not any
  chore that was created from it earlier).
- **Starter suggestions** (collapsed by default) — the bundled set,
  with a Hide button per row. Hiding a starter removes it from the
  library AND prevents it from being re-seeded on the next add-on
  restart.
- **Reset starter suggestions** (quiet link at the bottom) — restores
  every starter suggestion you've previously hidden. Your custom
  suggestions are untouched.

Editing a chore never modifies its source suggestion. Editing a
suggestion never modifies any chore that was previously created from
it. Suggestions are independent blueprints, not linked records.

### Library upgrades

Future versions of the add-on may ship new starter suggestions. When
they do, only the new ones get seeded into your existing library —
your customizations to existing entries are preserved, and starters
you've hidden stay hidden.

## Configuration

| Option | Default | Description |
|---|---|---|
| `log_level` | `info` | One of `debug`, `info`, `warning`, `error`. |
| `week_starts_on` | `monday` | Week-boundary day for `points_this_week`. `monday` or `sunday`. |
| `sound_default` | `false` | Whether the completion chime is on by default for new browser sessions. |
| `timezone` | `""` | Optional IANA name (e.g. `America/Los_Angeles`). Empty falls back to Home Assistant's configured timezone, fetched on startup. |

Changes to any option **restart** the add-on.

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
See [`INSTALL.md`](../INSTALL.md) "HA To-do Setup". Once you map a member to
their Local To-do entity, Family Chores manages items with `[FC#<id>]`
prefixes on that list; HA surfaces them on its calendar automatically.

## Dashboard integration

Three ways to surface Family Chores on a Home Assistant dashboard.

### The bundled Lovelace card

A lightweight Lit card surfaces each member's points, streak, and today's
progress on any HA dashboard. It reads HA entities only — never the
add-on's HTTP API. See [`lovelace-card/README.md`](../lovelace-card/README.md)
for install paths (the easiest is downloading `family-chores-card.js` from
the [latest GitHub release](https://github.com/japatton/family-chores/releases/latest)
and dropping it in `/config/www/`).

### Plain entity cards

If you'd rather build your own layout, use the published sensors directly:

```yaml
type: entities
title: Chores today
entities:
  - sensor.family_chores_alice_points
  - sensor.family_chores_bob_points
  - sensor.family_chores_carol_points
```

Each sensor's attributes (`points_this_week`, `streak`, `today_progress_pct`)
are available to template cards and gauges.

### Embed the full Ingress UI

The add-on's web UI is itself a dashboard surface — full kid-mode and
parent-mode flows. From a Lovelace dashboard:

```yaml
type: iframe
url: /hassio/ingress/family_chores
```

Or use a Picture Element / Button card with a tap-action that navigates to
`/hassio/ingress/family_chores`. The bundled Lovelace card uses the latter
pattern by default for its row tap-action.

## Events fired

| Event | Payload |
|---|---|
| `family_chores_completed` | `member_id`, `chore_id`, `instance_id`, `points` |
| `family_chores_approved` | same as above |
| `family_chores_streak_milestone` | `member_id`, `streak_days` |

Wire these to `tts.*`, lights, or notifications as you see fit.

## Backup and restore

### What's persisted

All add-on state lives in a single SQLite file at `/data/family_chores.db`
inside the container, which Home Assistant maps to
`/usr/share/hassio/addons/data/family_chores/` on the host. Members, chores,
completions, points, streaks, activity log — all of it lives there. The
`/data` volume survives:

- Add-on restarts.
- Add-on **updates** (the slug stays `family_chores` across versions, so HA
  reuses the same data directory).
- Container rebuilds.

It does **not** survive an explicit add-on uninstall unless HA's "keep
add-on data on uninstall" setting is enabled.

### Home Assistant snapshots

Home Assistant's full and partial backup flows include the add-on's `/data`
volume. To restore: **Settings → System → Backups →** restore the relevant
backup (the add-on entry under "partial backup" covers the SQLite file).

### The pre-migration safety copy

Before every Alembic migration, the add-on copies `/data/family_chores.db`
to `/data/family_chores.db.bak`. If a migration fails, restore the backup
file from `/usr/share/hassio/addons/data/family_chores/` on the host and
open an issue with the migration log.

The bootstrap also runs an integrity check on every start. A corrupt
database auto-restores from `family_chores.db.bak` when present; an empty
new DB is initialised when there's nothing to restore from. Either case
shows a banner in the UI and surfaces in `/api/info`.

### Manually copying the DB

For an out-of-band snapshot, stop the add-on first (so SQLite isn't
mid-write), copy the entire
`/usr/share/hassio/addons/data/family_chores/` directory (including
`family_chores.db-wal` and `family_chores.db-shm` if present), then
restart. WAL files contain pending writes — copying just
`family_chores.db` while the add-on is running gives you a partial
snapshot.

## Privacy

### What leaves the add-on

Nothing. The add-on only talks to:

1. The local browser of whoever's looking at the UI, over HA Ingress.
2. The Home Assistant Supervisor, to publish entity state and fire events.

It does not phone home, check for updates against any third-party service,
fetch remote assets, or send analytics. Updates flow through HA Supervisor
(which pulls from GHCR) and are explicit, user-initiated actions.

### What's stored on disk

- `family_chores.db` — the SQLite file with all family-member, chore,
  completion, and activity-log data.
- `family_chores.db.bak` — pre-migration safety copy (see Backup and
  restore above).
- Member avatars — the `Member.avatar` column holds a URL string only.
  An earlier spec called for an in-app upload + Pillow-re-encode path;
  that was never built and the dep was dropped (see F-S003 in the code
  review). When/if uploads land, EXIF stripping will land alongside.

### What's in the logs

The add-on log is verbose at `info` level (default) and verbose-er at
`debug`. Care has been taken to keep secrets out:

- Parent PIN hashes are never logged. The PIN itself is hashed with
  Argon2 before any code path can log it.
- Parent session JWTs are never logged.
- The `SUPERVISOR_TOKEN` HA provides on startup is never logged.
- Avatar file contents are never logged (only paths and counts).

If you're filing a bug report and want to share a log excerpt, check it
for member display names you'd rather not publish — those are logged at
`info` level on chore completion.

### Authentication scope

Once a parent unlocks the UI with the PIN, the resulting session token is
scoped to the browser that requested it (5-minute sliding TTL, extended
on activity via `/api/auth/refresh`). Closing the browser invalidates the
session.

## Troubleshooting

### Add-on won't start

Check the log for `Integrity check failed`. A corrupt database is
auto-restored from `/data/family_chores.db.bak` if one exists; otherwise
an empty DB is initialised and the UI shows a banner. If neither case
applies, look for an Alembic migration error and consult Backup and
restore above.

### Entities aren't updating in HA

The add-on keeps a retry queue for HA REST calls (cap 1000, drop-oldest).
Check the log for `ha.sync` entries. A periodic reconciler runs every 15
minutes as a safety net — if entities are stale longer than that, look
for HTTP 401s in the log (usually means the manifest's API permissions
changed) or repeated 5xx responses from Supervisor.

### Ingress panel is blank or stuck on "reconnecting…"

The SPA falls back to cached data if the WebSocket drops, and shows a
"reconnecting…" pill until it recovers. If it doesn't recover within a
minute or two:

- Check the add-on is actually running (Settings → Add-ons →
  Family Chores → status).
- Hard-refresh the browser (Cmd/Ctrl-Shift-R) to bypass the SPA cache.
- Check the add-on log for `WebSocket` errors.

### A chore I just added isn't showing up today

Newly-created chores generate today's instances inline — no waiting for
the midnight rollover. If a chore isn't appearing:

- Confirm it's assigned to a member (Parent → Chores → click the chore →
  check assignments).
- Confirm today matches the recurrence rule (a "weekdays" chore created
  on a Saturday won't surface until Monday).
- For `every_n_days` chores, check the anchor day — `every 3 days,
  anchor=Monday` only fires Mon, Thu, Sun, etc.

### Streak counter looks wrong

Streaks count days where the member completed *every* assigned chore.
Misses break the streak; days with no assigned chores don't break it.
The Parent → Activity tab shows the per-day chore-completion grid the
streak is computed from — useful when the count disagrees with what you
remember.

### Local-Todo items are duplicating or going stale

The reconciler runs every 15 minutes and on startup. Items the add-on
manages start with `[FC#<id>]`; items without that prefix are left alone.
If you see duplicates with the prefix:

- Make sure each member is mapped to **exactly one** Local-Todo entity in
  Parent → Members.
- If you renamed a Local-Todo entity in HA after mapping, update the
  member's mapping to the new entity ID.

## Support

- **Bug reports:** [open an issue](https://github.com/japatton/family-chores/issues/new?template=bug_report.yml). Attach the add-on log; do not share logs containing any `/data/options.json` secrets.
- **Feature requests:** read [`docs/roadmap.md`](../docs/roadmap.md) first, then [open one here](https://github.com/japatton/family-chores/issues/new?template=feature_request.yml).
- **Security reports:** see [`SECURITY.md`](../SECURITY.md). **Not** a public issue.
- **Usage questions:** [GitHub Discussions](https://github.com/japatton/family-chores/discussions).
