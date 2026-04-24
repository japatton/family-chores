# Family Chores Card

A tiny Lovelace card that surfaces each family member's points, streak, and today's progress from the entities published by the [Family Chores](https://github.com/japatton/family-chores) Home Assistant add-on.

The card reads Home Assistant state only — it never talks to the add-on's HTTP API, so your dashboard stays fast and the state model stays one-way.

## Requirements

- The [Family Chores add-on](https://github.com/japatton/family-chores) installed and running, with at least one family member configured.
- Home Assistant 2023.6 or newer.

## What it shows

- One row per family member, auto-discovered from `sensor.family_chores_<slug>_points` entities.
- Current streak and points-this-week for each member.
- A progress ring showing today's completion rate.
- An optional badge when one or more chores are awaiting parent approval.
- Tap a row to jump into the Family Chores Ingress UI.

## Minimal configuration

```yaml
type: custom:family-chores-card
```

The GUI editor (opened from HA's card picker) covers the common options. See the [full card documentation](https://github.com/japatton/family-chores/blob/main/lovelace-card/README.md) for every configuration key.

## Links

- [Add-on repository](https://github.com/japatton/family-chores)
- [Add-on documentation](https://github.com/japatton/family-chores/blob/main/family_chores/DOCS.md)
- [Report a card bug](https://github.com/japatton/family-chores/issues/new?template=bug_report.yml)
