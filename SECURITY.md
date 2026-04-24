# Security policy

Family Chores is a self-hosted Home Assistant add-on. The threat model and disclosure process below reflect that — this is not a multi-tenant cloud service, and the relevant security boundary is your Home Assistant install, not the add-on itself.

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security reports.

The two acceptable channels are, in order of preference:

1. **GitHub Security Advisories** — go to the repository's **Security** tab → **Report a vulnerability**. Private until you and the maintainer agree to publish.
2. **Email** — `YOUR_CONTACT_EMAIL_HERE`. PGP not currently supported; please send a brief summary first and I'll ask for details over a more secure channel if warranted.

Include:

- Affected version(s) — the `version:` field in `family_chores/config.yaml` of the install you reproduced against. If you're not sure, the latest tagged release is fine.
- A description of the issue and the impact you've confirmed (not the impact you suspect).
- Steps to reproduce, ideally against a fresh install or a synthetic dev setup. The `./scripts/dev_backend.sh` + `./scripts/dev_frontend.sh` flow described in [`CONTRIBUTING.md`](CONTRIBUTING.md) is reproducible without a real HA instance.
- Any logs, request/response captures, or proof-of-concept code that helped you confirm the issue. Strip any personal data first.

I'll acknowledge receipt within **5 business days** and aim to either confirm/fix or explain why the report falls outside scope within **30 days**. For severe issues with active exploitation potential, the timeline tightens — flag the urgency in your report and we'll coordinate.

If you don't hear back in those windows, a polite nudge to the same channel is welcome. Personal project, occasional vacations, no on-call rotation.

## Scope

In scope:

- The add-on's HTTP API (`/api/...`), WebSocket endpoint (`/api/ws`), and Ingress-served SPA at the add-on's panel URL.
- The add-on's interaction with Home Assistant via the Supervisor proxy (token handling, request signing, retry logic).
- The add-on's SQLite layer: SQL injection paths, file-permission issues on `/data/family_chores.db`, integrity check / recovery flow.
- The Lovelace card's read-only consumption of HA entities published by the add-on.
- Dependencies declared in `family_chores/pyproject.toml`, `packages/*/pyproject.toml`, `family_chores/frontend/package.json`, `lovelace-card/package.json`.

**Out of scope** — these are documented design decisions, not vulnerabilities:

- The **parent PIN is a soft lock**, not a security boundary. Documented in [`README.md`](README.md), [`family_chores/DOCS.md`](family_chores/DOCS.md), and [`DECISIONS.md`](DECISIONS.md) §4 #11. Reports of "I bypassed the PIN by clearing localStorage" or "the PIN can be brute-forced" describe the design, not a vulnerability.
- The add-on runs **inside Home Assistant's trust boundary**. Anyone who can reach your HA install can reach the add-on. Reports of "an authenticated HA user can use the add-on" describe the design.
- The add-on **does not authenticate Ingress requests independently** — it trusts HA Supervisor's `X-Remote-User` header on Ingress requests. Reports that this header can be forged from inside the HA host are out of scope; a host-level compromise is already game over.
- HA Supervisor itself, Home Assistant Core, the underlying base-python image, or any other Home Assistant component. Report those upstream.
- Social engineering, physical access to the wall-mounted tablet, or phishing.

## Supported versions

Only the **latest tagged release** is supported for security fixes. The current release is in [`family_chores/CHANGELOG.md`](family_chores/CHANGELOG.md) and on the [GitHub Releases](https://github.com/japatton/family-chores/releases) page.

If you're running an older version, the upgrade path is to install the latest. Backports of security fixes are not provided.

## Disclosure

Once a fix is shipped in a tagged release, the corresponding GitHub Security Advisory will be published with a CVE if one was assigned and credit to the reporter (unless they've asked to remain anonymous). The advisory will name the affected versions, the fixed version, and the workaround (if any) for users who can't upgrade immediately.

If 90 days pass after report acknowledgement without a fix or a confirmed not-a-vulnerability response, the reporter is welcome to publish on their own schedule — though a heads-up beforehand is appreciated.
