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

### Manual

1. Build the card:
   ```sh
   cd lovelace-card
   npm install
   npm run build
   ```
2. Copy `dist/family-chores-card.js` into your HA config directory at
   `/config/www/family-chores-card.js` (Samba, SSH, or the File editor
   add-on all work).
3. In **Settings → Dashboards → ⋮ → Resources**, add:
   - URL: `/local/family-chores-card.js`
   - Type: `JavaScript Module`
4. Refresh the browser. You can now add the card via the **+ Add Card**
   picker; it appears as "Family Chores".

### HACS

HACS support will land with milestone 8 / release automation.

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
