# Calendar integration

Family Chores can read events from Home Assistant `calendar.*` entities and surface them next to chores so the kid sees, at a glance, what they need to bring or wear today and what's happening this month.

This doc covers wiring it up, what kids see, what parents see, and the architecture for contributors. For the design journal see [DECISIONS.md §14](../DECISIONS.md).

## What it gives you

**On the parent's home tile (`/`)**
- A "Next: 4:00 PM · Soccer" hint for the next non-all-day event today.
- A chip strip with what each kid needs to bring today (cleats, water bottle, lunch, …) — auto-extracted from event descriptions.
- A small "couldn't reach a calendar" warning when one of the kid's calendars failed to fetch (network blip, HA upgrade window, etc.).

**On the kid's view (`/member/<slug>`)**
- A "Today's events" panel below the chore list with start time, summary, location, and prep chips.
- All-day events get an "All day" badge instead of pretending to be at midnight.
- Past events are filtered server-side so the kid never sees "Soccer (4 PM)" at 9 PM.

**On the parent's calendar tab (`/parent/calendar`)**
- A monthly grid covering all family events in one view, click a day to see details.
- A settings panel to wire up household-shared and per-member `calendar.*` entity ids.
- A refresh button that busts the 60-second cache so freshly-added HA events show up immediately.

## Wiring it up

Calendars live in Home Assistant — Family Chores reads them via the `calendar.get_events` service. Anything that exposes a `calendar.*` entity (CalDAV, Google Calendar, Local Calendar, the Holiday integration, etc.) works.

1. Open **Parent mode → Calendar** in Family Chores.
2. Add the `calendar.*` entity ids you want surfaced:
   - **Family-shared** calendars appear on every member's tile + view (good for "Family dinner" or holiday spans).
   - **Per-member** calendars only appear for that one kid (good for "Alice's soccer" or "Bob's piano").
3. Click "🔄 Refresh" if you just added the entity ids and don't want to wait the 60-second TTL.

That's it. The kid view and the home tile will start showing events the next time the page polls.

> **Tip — find HA entity ids**: in HA, open Developer Tools → States and filter by `calendar.`. Each row's `entity_id` column is what you paste into Family Chores.

## Prep items — power-user format

Family Chores tries to extract "what to bring" from event descriptions so the kid sees a chip on their tile.

**Two ways to write it:**

**Explicit (recommended for unambiguous extraction):**

```
[prep: cleats, water bottle, snack]
```

Wins over verb detection. Use commas or " and " between items. The label appears verbatim on the kid's chip, so write it the way the kid will recognise it.

**Verb fallback (for the 80% case):**

```
Bring cleats and water bottle
Wear uniform
Pack lunch
Don't forget homework
```

Sentence-anchored on `bring|wear|pack|don't forget`. Captures the noun phrase up to the next punctuation or clause break (so "Bring lunch to school" yields just "lunch", not "lunch to school"). Splits on commas and " and " to extract multiple items.

The explicit `[prep:]` tag bypasses verb detection — if you tagged, Family Chores trusts you and ignores stray verbs.

**Icons** auto-attach for ~25 common kid items: backpack, cleats, water bottle, lunch, snack, homework, sunscreen, swimsuit, towel, instrument, etc. Unknown items render text-only — no icon, just the label.

## Architecture (for contributors)

The calendar layer ships in four layers, top-down:

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend                                                     │
│   MonthGrid · CalendarDayList · PrepChipStrip                │
│   CalendarTab (parent) · MemberView Today section (kid)      │
└──────────────┬──────────────────────────────────────────────┘
               │ /api/today (chips + Today section)
               │ /api/calendar/events (monthly view)
               │ /api/household/settings + /api/calendar/refresh
┌──────────────▼──────────────────────────────────────────────┐
│ packages/api/services/calendar/                              │
│   get_events_for_window(provider, cache, …)                  │
│   partition_by_member · hide_past · prep parser              │
└──────────────┬──────────────────────────────────────────────┘
               │ CalendarProvider Protocol
┌──────────────▼──────────────────────────────────────────────┐
│ family_chores/ha/calendar.py                                 │
│   HACalendarProvider — wraps HAClient.call_service           │
│   ("calendar", "get_events", …)                              │
└──────────────┬──────────────────────────────────────────────┘
               │ HTTP
        Home Assistant Supervisor → calendar.* entities
```

### Provider Protocol seam

`CalendarProvider` (`packages/api/services/calendar/provider.py`) is a `Protocol` with one method:

```python
async def get_events(
    self,
    entity_ids: list[str],
    from_dt: datetime,
    to_dt: datetime,
) -> CalendarProviderResult: ...
```

The addon ships `HACalendarProvider`. The SaaS scaffold (`apps/saas-backend/`) wires `NoOpCalendarProvider` until a CalDAV / Google Calendar provider lands in Tier 2 of the [decoupling roadmap](#decoupling-tiers). The composition service in `packages/api` doesn't know or care which is plugged in.

`CalendarProviderResult` carries both `events` and `unreachable: list[str]` so a single broken calendar surfaces as a per-tile error rather than failing the whole request.

### Cache

`CalendarCache` (`packages/api/services/calendar/cache.py`) is a 60-second TTL keyed by `(entity_id, day)`. It's:

- **Per-process / in-memory** — the addon runs as a single uvicorn worker so there's no cross-worker coordination needed. A future SaaS deployment that scales horizontally would swap this for Redis against the same Protocol.
- **Manually invalidated** by:
  - `POST /api/calendar/refresh` (parent's button)
  - Any `PUT /api/household/settings` that changes `shared_calendar_entity_ids`
  - Any `PATCH /api/members/{slug}` that changes `calendar_entity_ids`
- **Eviction-on-access** — stale entries are dropped when read, no background sweeper.

### Prep parser

Pure module (`packages/api/services/calendar/prep.py`) — no I/O, no DB, no logging. Two passes:

1. **Explicit `[prep: ...]` tag** wins. Splits on commas and ` and `. Respects parent's exact wording.
2. **Verb fallback** — `bring|wear|pack|don't forget` regex with sentence-anchored capture, clause-break truncation at prepositions (`to|for|at|on|in|by|with|from|of|before|after|until|because`), and dedup across patterns by normalised label.

Icon dictionary maps ~25 common kid items to emoji. Multi-word entries (`water bottle` → 💧) are tried before single-word fallback.

### `/api/today` extension

`TodayMember` (`packages/api/schemas.py`) carries:

```python
calendar_events: list[CalendarEventRead]
calendar_unreachable: list[str]
```

The endpoint resolves each member's entity ids (per-member + household-shared), de-dupes across members for one batched provider call, partitions events back per-member with shared events appearing under each owner, and runs `hide_past` against tz-aware "now" so a 9am event still shows at 8:59am.

**Calendar fetch is best-effort.** A provider exception, the calendar service raising, anything — the chore list still renders. The kid view must NEVER fail because of a calendar issue.

### Frontend components

- `PrepChipStrip` — compact, parent-home tile. De-dupes prep items across all of today's events for the member; collapses past `maxChips` into a "+N more" pill.
- `CalendarDayList` — full panel for `MemberView`. One card per event with start time, summary, optional location, and prep chips. Empty list collapses to a single line; unreachable hint at the top when applicable.
- `MonthGrid` — 6×7 day cell grid. Up to 3 event chips per cell with overflow pill, today highlight, selected-day ring outline.
- `CalendarEntityIdsEditor` — chip add/remove for `calendar.*` ids. Used by both the household-shared section and the per-member rows.
- `CalendarTab` (in `views/parent/`) — composes the monthly grid + side panel + settings.

## Decoupling tiers

The Calendar Protocol is the first step in a longer-term decoupling roadmap captured in DECISIONS §14. The four tiers, in increasing scope:

| Tier | Scope | Status |
|------|-------|--------|
| **1** | Provider abstractions (`CalendarProvider`, `TodoProvider`) so the addon's HA-specific code is swappable | **Done** in v0.5.0 |
| **2** | Standalone Docker target — same code, no HA. Needs a non-HA calendar provider (CalDAV / Google Calendar / Microsoft Calendar) and a non-HA todo provider (or NoOp). | Open |
| **3** | SaaS-grade — multi-tenant Postgres, OAuth identity, observability. The current `apps/saas-backend/` scaffold is a placeholder. | Open |
| **4** | Mobile-first — native iOS/Android consuming the same API surface. | Open |

Tier 1 makes Tier 2+ possible without rewriting the addon. The current Protocols deliberately match the HA service surface (so the wrapping is thin); a CalDAV implementation will need to translate event recurrence at its layer.

## Known limits

- **HA-specific**: the only provider that ships today is `HACalendarProvider`. A standalone (non-HA) deployment gets the no-op, which means no events. Tier 2 fixes this.
- **No write path**: Family Chores reads calendars but doesn't create or modify events. If you want "calendar event triggered → chore added", that lives in HA automations (the addon's events surface gives you `family_chores_*` triggers but not the inverse).
- **No per-event color picker yet**: events on the monthly grid all share the brand color dot. A "color this calendar pink" UI is a fast follow if there's demand.
- **One uvicorn worker**: the cache is in-process. Multi-worker scaling is a Tier 3 concern.

## Where to file calendar issues

- **Bugs in event display, prep extraction, or settings UI** — [GitHub Issues](https://github.com/japatton/family-chores/issues), use the `bug_report.yml` template.
- **A calendar entity that won't render** — first verify it works in HA's Calendar dashboard (i.e. that the underlying calendar integration itself is healthy). If yes, file a bug with the entity id and a redacted screenshot of one event from HA's dev tools.
- **Asks for a non-HA backend** — Tier 2 work. Open a discussion thread describing your deployment so the design weights real demand.
