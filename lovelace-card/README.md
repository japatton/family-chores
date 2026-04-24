# family-chores-card

A tiny Lovelace card that surfaces each family member's points, streak, and
today's progress from the entities published by the **Family Chores**
Home Assistant add-on. Reads HA state only — it never talks to the add-on's
HTTP API, so your dashboard stays fast and the state model stays one-way.

## What it shows

- One row per discovered family member (any entity named
  `sensor.family_chores_<slug>_points`)
- Streak and points-this-week from the sensor's attributes
- A progress ring for today
- Optional "N to approve" badge when
  `sensor.family_chores_pending_approvals` is > 0
- Tap anywhere navigates to the Family Chores Ingress app

## Install

Three paths, in order of ease.

### From a GitHub Release (recommended)

The release workflow attaches a pre-built `family-chores-card.js` to every
tagged release, so you don't need Node installed.

1. Open the [latest release](https://github.com/japatton/family-chores/releases/latest)
   and download `family-chores-card.js` from the **Assets** section.
2. Copy it into your HA config directory at
   `/config/www/family-chores-card.js` (Samba, SSH, or the File editor
   add-on all work).
3. In **Settings → Dashboards → ⋮ → Resources**, add:
   - URL: `/local/family-chores-card.js?v=<release-version>`
   - Type: `JavaScript Module`
4. Refresh the browser. Add the card via **+ Add Card** → "Family Chores".

The `?v=<release-version>` query string is a cache-buster — bump it when you
upgrade so HA reloads the module.

### HACS (custom repository)

The card ships HACS metadata (`hacs.json`, `info.md`) so it's ready for
HACS custom-repository install. Because this monorepo houses both the
add-on and the card, HACS default-list inclusion requires a standalone
card-only repo — see [`docs/roadmap.md`](../docs/roadmap.md) for status.
Until then, use one of the other two install paths.

### From source

1. Clone the repo and build:
   ```sh
   git clone https://github.com/japatton/family-chores
   cd family-chores
   pnpm install --frozen-lockfile
   pnpm --filter family-chores-card build
   ```
   (Or, standalone without pnpm: `cd lovelace-card && npm install && npm run build`.)
2. Copy `lovelace-card/dist/family-chores-card.js` into your HA config
   directory at `/config/www/family-chores-card.js`.
3. Register the resource and add the card per steps 3 and 4 above.

## Configuration

Minimal:
```yaml
type: custom:family-chores-card
```

All options:
```yaml
type: custom:family-chores-card
title: Chores
members:
  - alice
  - bob
show_pending_approvals: true
tap_action:
  action: navigate
  navigation_path: /hassio/ingress/local_family_chores
```

- `title` — card heading; defaults to "Family Chores".
- `members` — list of family-member slugs to include; omit to show all
  discovered members.
- `show_pending_approvals` — if `true` (default), shows a warning-colour
  badge when any instance is in `done_unapproved`.
- `tap_action.navigation_path` — where to send the user when they tap a
  row. Default is `/hassio/ingress/local_family_chores`, which is what
  Supervisor assigns by default. Override if your add-on slug differs.

The card also ships a GUI editor (`family-chores-card-editor`) that HA's
card picker opens automatically — no YAML required for the basics.

## Why a separate card

The add-on could render its own widget inside an iframe, but that:
- Makes dashboards blank while the add-on is slow
- Couples the dashboard to the add-on's auth / Ingress path
- Can't be styled to match HA's theme

A native Lovelace card sidesteps all three. It's also a clean forcing
function: if the bridge isn't working, the card silently shows no rows —
which tells you a real thing about the add-on's state.
