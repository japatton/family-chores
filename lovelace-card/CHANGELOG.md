# Changelog

All notable changes to the Family Chores Lovelace card.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the card adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The card is versioned independently from the add-on. The add-on's
[CHANGELOG](../family_chores/CHANGELOG.md) describes what the add-on
publishes; this file describes what the card reads.

## [0.1.0] — 2026-04-23

### Added

- Initial release, shipped alongside the Family Chores add-on v0.2.0.
- One row per family member, auto-discovered from
  `sensor.family_chores_<slug>_points` entities.
- Streak, weekly points, and today's-progress ring for each row.
- Optional badge for pending parent approvals, driven by
  `sensor.family_chores_pending_approvals`.
- Tap action defaults to the Family Chores Ingress path; overridable per
  install.
- GUI editor (`family-chores-card-editor`) so basic configuration doesn't
  require touching YAML.
- Built as a single-file minified module (~26 KB) via Rollup; ships `lit`
  as the only runtime dependency.
- HACS metadata (`hacs.json`, `info.md`) prepared for future custom-repository
  publication — see the card [README](README.md) for current install paths.
