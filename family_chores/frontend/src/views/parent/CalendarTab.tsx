import { useMemo, useState } from 'react'
import { APIError } from '../../api/client'
import {
  useCalendarEvents,
  useHouseholdSettings,
  useMembers,
  useRefreshCalendar,
  useUpdateHouseholdSettings,
  useUpdateMember,
} from '../../api/hooks'
import type { CalendarEvent, Member } from '../../api/types'
import { CalendarDayList } from '../../components/CalendarDayList'
import { CalendarEntityIdsEditor } from '../../components/CalendarEntityIdsEditor'
import { MonthGrid } from '../../components/MonthGrid'

/**
 * Parent's calendar surface (DECISIONS §14 PR-C). Two stacked
 * sections:
 *
 *   1. Monthly grid — all events across all family members for the
 *      visible month. Click a day with events to open a side panel
 *      with the full event list (reuses `CalendarDayList`).
 *   2. Settings — household-shared calendar list + per-member
 *      mappings. Lets the parent wire up entity ids without leaving
 *      the calendar tab.
 *
 * Refresh button at the top busts both the server-side cache and the
 * TanStack Query cache so a freshly-added HA event shows up
 * immediately rather than waiting on the 60s TTL.
 */
export function CalendarTab() {
  const [monthAnchor, setMonthAnchor] = useState<Date>(_thisMonthStart())
  const [selectedDate, setSelectedDate] = useState<Date | null>(null)

  const { fromIso, toIso } = useMemo(
    () => _monthWindow(monthAnchor),
    [monthAnchor],
  )
  const events = useCalendarEvents(fromIso, toIso)
  const refresh = useRefreshCalendar()

  const today = useMemo(() => new Date(), [])

  const eventsByDay = useMemo(() => {
    if (selectedDate === null) return [] as CalendarEvent[]
    if (!events.data) return [] as CalendarEvent[]
    const key = _dayKey(selectedDate)
    return events.data.events.filter(
      (e) => _dayKey(new Date(e.start)) === key,
    )
  }, [events.data, selectedDate])

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setMonthAnchor(_addMonths(monthAnchor, -1))}
            className="min-h-touch min-w-touch px-4 rounded-2xl bg-brand-50 text-brand-700 font-bold text-fluid-sm grid place-items-center"
            aria-label="Previous month"
          >
            ←
          </button>
          <h2 className="text-fluid-lg font-black text-brand-900 min-w-[10rem] text-center">
            {_monthLabel(monthAnchor)}
          </h2>
          <button
            type="button"
            onClick={() => setMonthAnchor(_addMonths(monthAnchor, 1))}
            className="min-h-touch min-w-touch px-4 rounded-2xl bg-brand-50 text-brand-700 font-bold text-fluid-sm grid place-items-center"
            aria-label="Next month"
          >
            →
          </button>
          <button
            type="button"
            onClick={() => {
              setMonthAnchor(_thisMonthStart())
              setSelectedDate(null)
            }}
            className="min-h-touch px-4 rounded-2xl bg-brand-50 text-brand-700 font-bold text-fluid-sm grid place-items-center"
          >
            Today
          </button>
        </div>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="min-h-touch px-5 rounded-2xl bg-brand-600 text-white font-black text-fluid-sm disabled:opacity-50"
        >
          {refresh.isPending ? 'Refreshing…' : '🔄 Refresh'}
        </button>
      </header>

      {events.error && (
        <div role="alert" className="rounded-xl bg-rose-50 px-4 py-3 text-rose-800 text-fluid-sm font-semibold">
          Couldn't load calendar events. Check the addon log + your HA token.
        </div>
      )}
      {events.data && events.data.unreachable.length > 0 && (
        <div role="status" className="rounded-xl bg-amber-100 px-4 py-3 text-amber-800 text-fluid-sm font-semibold">
          Couldn't reach: {events.data.unreachable.join(', ')}
        </div>
      )}

      <div className="grid lg:grid-cols-[2fr_1fr] gap-6">
        <MonthGrid
          monthStart={monthAnchor}
          today={today}
          selectedDate={selectedDate}
          events={events.data?.events ?? []}
          onSelectDate={(d) => setSelectedDate(d)}
        />

        {/* Side panel — selected day detail or "tap a day" prompt. */}
        <aside className="space-y-3">
          {selectedDate ? (
            <>
              <header className="flex items-center justify-between">
                <h3 className="text-fluid-base font-black text-brand-900">
                  {selectedDate.toLocaleDateString(undefined, {
                    weekday: 'long',
                    month: 'long',
                    day: 'numeric',
                  })}
                </h3>
                <button
                  type="button"
                  onClick={() => setSelectedDate(null)}
                  className="min-h-touch px-3 rounded-xl bg-brand-50 text-brand-700 font-bold text-fluid-xs"
                >
                  Clear
                </button>
              </header>
              <CalendarDayList events={eventsByDay} />
            </>
          ) : (
            <div className="rounded-xl4 bg-brand-50 px-5 py-8 text-center text-fluid-sm font-semibold text-brand-700/80">
              Tap a day with events to see details.
            </div>
          )}
        </aside>
      </div>

      <CalendarSettingsPanel />
    </div>
  )
}

function CalendarSettingsPanel() {
  const settings = useHouseholdSettings()
  const updateSettings = useUpdateHouseholdSettings()
  const members = useMembers()
  const [error, setError] = useState<string | null>(null)

  if (settings.isLoading || members.isLoading) {
    return <p className="text-brand-700">Loading calendar settings…</p>
  }

  const sharedIds = settings.data?.shared_calendar_entity_ids ?? []

  const saveShared = (next: string[]) => {
    setError(null)
    updateSettings.mutate(
      { shared_calendar_entity_ids: next },
      {
        onError: (e) => {
          setError(e instanceof APIError ? e.detail : 'Failed to save settings.')
        },
      },
    )
  }

  return (
    <section className="rounded-xl4 bg-white p-5 sm:p-6 shadow-card space-y-6">
      <header>
        <h3 className="text-fluid-lg font-black text-brand-900">Calendar settings</h3>
        <p className="text-fluid-xs text-brand-700/70 mt-1">
          Wire HA <span className="font-mono">calendar.*</span> entities here.
          Shared calendars show on every member; per-member calendars only
          show on that kid's view.
        </p>
      </header>

      <div>
        <CalendarEntityIdsEditor
          label="Family-shared calendars"
          hint="These appear on every member's tile and the kid's Today view."
          value={sharedIds}
          onChange={saveShared}
          disabled={updateSettings.isPending}
        />
      </div>

      <div className="space-y-4">
        <h4 className="text-fluid-base font-black text-brand-900">
          Per-member calendars
        </h4>
        <ul className="space-y-3">
          {(members.data ?? []).map((m) => (
            <PerMemberCalendarRow key={m.id} member={m} />
          ))}
        </ul>
      </div>

      {error && (
        <div role="alert" className="text-rose-600 text-fluid-sm font-semibold">
          {error}
        </div>
      )}
    </section>
  )
}

function PerMemberCalendarRow({ member }: { member: Member }) {
  const update = useUpdateMember(member.slug)
  const [error, setError] = useState<string | null>(null)

  return (
    <li
      className="rounded-2xl bg-brand-50/50 p-4 space-y-3"
      style={{ borderLeft: '6px solid ' + member.color }}
    >
      <div className="flex items-center gap-3">
        <span aria-hidden className="text-fluid-base">
          {member.avatar ?? '🧒'}
        </span>
        <span className="text-fluid-base font-black text-brand-900">
          {member.name}
        </span>
      </div>
      <CalendarEntityIdsEditor
        value={member.calendar_entity_ids}
        onChange={(next) => {
          setError(null)
          update.mutate(
            { calendar_entity_ids: next },
            {
              onError: (e) => {
                setError(
                  e instanceof APIError ? e.detail : 'Failed to save mapping.',
                )
              },
            },
          )
        }}
        disabled={update.isPending}
      />
      {error && (
        <div role="alert" className="text-rose-600 text-fluid-xs font-semibold">
          {error}
        </div>
      )}
    </li>
  )
}

// ─── helpers ───────────────────────────────────────────────────────────

function _thisMonthStart(): Date {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

function _addMonths(d: Date, delta: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + delta, 1)
}

function _monthLabel(d: Date): string {
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

function _monthWindow(monthAnchor: Date): {
  fromIso: string
  toIso: string
} {
  // Six rows of seven days = 42 cells, starting from the most recent
  // Monday on or before the 1st. We mirror that here so the fetch
  // covers exactly what the grid renders (avoids "Why is this Apr 30
  // event missing from May's grid?").
  const firstOfMonth = new Date(
    monthAnchor.getFullYear(),
    monthAnchor.getMonth(),
    1,
  )
  const offset = (firstOfMonth.getDay() + 6) % 7 // Monday-first
  const start = new Date(firstOfMonth)
  start.setDate(start.getDate() - offset)
  const end = new Date(start)
  end.setDate(end.getDate() + 42)
  // ISO 8601 with offset; the Date.toISOString gives UTC which is
  // exactly what the API expects.
  return { fromIso: start.toISOString(), toIso: end.toISOString() }
}

function _dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}
