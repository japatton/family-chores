import { useMemo } from 'react'
import type { CalendarEvent } from '../api/types'

interface MonthGridProps {
  /** First day of the month being rendered. Day-of-month and time
   * components are ignored — only year + month + tz matter. */
  monthStart: Date
  events: CalendarEvent[]
  /** Date the user is highlighting. Optional; defaults to "no
   * highlight". Compared by local Y-M-D, not timestamp. */
  selectedDate?: Date | null
  /** Today's date for the today-highlight. Optional so consumers can
   * pin it for testing. Defaults to `new Date()` at render time. */
  today?: Date
  /** Per-event color lookup keyed by entity_id (parent picks colors
   * in the settings panel). Falls back to brand-500 when no mapping. */
  colorByEntity?: Record<string, string>
  /** Click on a non-empty day cell. Optional — without it the cells
   * are display-only. */
  onSelectDate?: (date: Date) => void
  /** Week start: 0 = Sunday, 1 = Monday. Default 1 to match the
   * rest of the app's `week_starts_on=monday` convention. */
  weekStartsOn?: 0 | 1
}

/**
 * 6-row × 7-column grid of day cells for one month (DECISIONS §14
 * PR-C). Each cell shows up to three event chips with a "+N more"
 * overflow indicator; click opens a day detail (handled by parent).
 *
 * Pure presentation — fetching, window selection, and selected-day
 * panel live in the consuming view. The component only knows how to
 * lay out a grid given a month and an event list.
 */
export function MonthGrid({
  monthStart,
  events,
  selectedDate,
  today,
  colorByEntity,
  onSelectDate,
  weekStartsOn = 1,
}: MonthGridProps) {
  const referenceToday = useMemo(() => today ?? new Date(), [today])

  // Build the 42 day cells (6 rows × 7 cols). The first cell is the
  // most recent `weekStartsOn` weekday on or before the 1st, so the
  // grid always starts on the configured week-start.
  const cells = useMemo<DayCell[]>(() => {
    return _buildMonthCells(monthStart, weekStartsOn)
  }, [monthStart, weekStartsOn])

  // Bucket events by local Y-M-D so day cells can render their
  // matching events in O(1). Multi-day events (rare in our domain
  // — mostly all-day "Spring Break" spans) are repeated under each
  // day they intersect.
  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>()
    for (const event of events) {
      for (const dayKey of _eventDayKeys(event)) {
        const list = map.get(dayKey) ?? []
        list.push(event)
        map.set(dayKey, list)
      }
    }
    return map
  }, [events])

  const weekdayLabels = useMemo(
    () => _weekdayLabels(weekStartsOn),
    [weekStartsOn],
  )

  return (
    <div className="rounded-xl4 bg-white shadow-card overflow-hidden">
      <div
        className="grid grid-cols-7 border-b border-brand-100 text-fluid-xs font-bold text-brand-700/70 uppercase tracking-wide"
        role="row"
      >
        {weekdayLabels.map((label) => (
          <div
            key={label}
            role="columnheader"
            className="px-2 py-2 text-center"
          >
            {label}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7" role="grid">
        {cells.map((cell) => (
          <DayCell
            key={_dayKey(cell.date)}
            cell={cell}
            isCurrentMonth={cell.date.getMonth() === monthStart.getMonth()}
            isToday={_sameYMD(cell.date, referenceToday)}
            isSelected={
              selectedDate ? _sameYMD(cell.date, selectedDate) : false
            }
            events={eventsByDay.get(_dayKey(cell.date)) ?? []}
            colorByEntity={colorByEntity}
            onSelect={onSelectDate}
          />
        ))}
      </div>
    </div>
  )
}

interface DayCell {
  date: Date
}

interface DayCellProps {
  cell: DayCell
  isCurrentMonth: boolean
  isToday: boolean
  isSelected: boolean
  events: CalendarEvent[]
  colorByEntity?: Record<string, string>
  onSelect?: (date: Date) => void
}

function DayCell({
  cell,
  isCurrentMonth,
  isToday,
  isSelected,
  events,
  colorByEntity,
  onSelect,
}: DayCellProps) {
  const visible = events.slice(0, 3)
  const overflow = events.length - visible.length
  const dayNumber = cell.date.getDate()

  const interactive = events.length > 0 && onSelect !== undefined
  const Wrapper = interactive ? 'button' : 'div'

  return (
    <Wrapper
      type={interactive ? 'button' : undefined}
      role="gridcell"
      onClick={interactive ? () => onSelect!(cell.date) : undefined}
      // Selected day gets a ring, today gets a coloured chip on the
      // day number, off-month days fade. The min-height keeps the
      // grid uniform even on weeks with no events.
      className={[
        'group relative min-h-[5.5rem] sm:min-h-[6.5rem] border-b border-r border-brand-100 px-2 py-1.5 text-left',
        // Last column drops the right border for a cleaner edge.
        '[&:nth-child(7n)]:border-r-0',
        isCurrentMonth ? 'bg-white' : 'bg-brand-50/40',
        isSelected ? 'ring-2 ring-brand-500 ring-inset' : '',
        interactive ? 'hover:bg-brand-50 focus-visible:bg-brand-50 focus-visible:outline-none' : '',
      ].join(' ')}
      aria-label={
        events.length === 0
          ? cell.date.toDateString()
          : `${cell.date.toDateString()} — ${events.length} event${events.length === 1 ? '' : 's'}`
      }
    >
      <div className="flex items-center justify-between">
        <span
          className={[
            'inline-grid place-items-center min-w-[1.75rem] h-7 rounded-full text-fluid-xs font-bold',
            isToday
              ? 'bg-brand-600 text-white px-1.5'
              : isCurrentMonth
                ? 'text-brand-900'
                : 'text-brand-700/40',
          ].join(' ')}
        >
          {dayNumber}
        </span>
        {events.length > 0 && (
          <span
            aria-hidden
            className="text-[0.65rem] font-bold text-brand-700/60"
          >
            {events.length}
          </span>
        )}
      </div>
      <ul className="mt-1 space-y-0.5">
        {visible.map((event, idx) => (
          <li
            key={`${event.entity_id}-${event.start}-${idx}`}
            className="flex items-center gap-1 text-[0.7rem] sm:text-fluid-xs font-semibold truncate"
          >
            <span
              aria-hidden
              className="inline-block size-2 rounded-full shrink-0"
              style={{
                background:
                  colorByEntity?.[event.entity_id] ?? 'rgb(99 102 241)',
              }}
            />
            <span className="truncate text-brand-900">
              {event.all_day ? event.summary : `${_timeShort(event.start)} ${event.summary}`}
            </span>
          </li>
        ))}
        {overflow > 0 && (
          <li className="text-[0.7rem] sm:text-fluid-xs font-bold text-brand-700/70">
            +{overflow} more
          </li>
        )}
      </ul>
    </Wrapper>
  )
}

// ─── helpers ───────────────────────────────────────────────────────────

function _buildMonthCells(monthStart: Date, weekStartsOn: 0 | 1): DayCell[] {
  // Step back from the 1st to the most recent week-start day. JavaScript's
  // getDay returns 0 for Sunday, 1 for Monday, ..., 6 for Saturday.
  // For weekStartsOn=1: offset = (day - 1 + 7) % 7
  // For weekStartsOn=0: offset = day
  const firstOfMonth = new Date(
    monthStart.getFullYear(),
    monthStart.getMonth(),
    1,
  )
  const offset =
    weekStartsOn === 1
      ? (firstOfMonth.getDay() + 6) % 7
      : firstOfMonth.getDay()
  const start = new Date(firstOfMonth)
  start.setDate(start.getDate() - offset)

  const cells: DayCell[] = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    cells.push({ date: d })
  }
  return cells
}

function _eventDayKeys(event: CalendarEvent): string[] {
  // For all-day events HA conventionally returns end as the day AFTER
  // the last visible day (DTSTART = inclusive, DTEND = exclusive). We
  // match that: a span from May 1 to May 8 means 7 visible days
  // (May 1 through May 7).
  const start = new Date(event.start)
  const end = new Date(event.end)
  const keys: string[] = [_dayKey(start)]
  if (event.all_day) {
    const cursor = new Date(start)
    cursor.setDate(cursor.getDate() + 1)
    while (cursor < end) {
      keys.push(_dayKey(cursor))
      cursor.setDate(cursor.getDate() + 1)
    }
  } else {
    // Timed events that span midnight: re-add for each subsequent day
    // up to (but not including) the end day.
    const startKey = _dayKey(start)
    const cursor = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 1)
    while (cursor < end) {
      const key = _dayKey(cursor)
      if (key !== startKey && !keys.includes(key)) keys.push(key)
      cursor.setDate(cursor.getDate() + 1)
    }
  }
  return keys
}

function _dayKey(d: Date): string {
  // Local-time Y-M-D. Used as a Map key — comparing across tz would
  // mis-bucket events that happen near midnight in the user's locale.
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
}

function _sameYMD(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function _timeShort(iso: string): string {
  // "9:30 AM" or "16:00" depending on user locale. Compact for the cell.
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}

function _weekdayLabels(weekStartsOn: 0 | 1): string[] {
  // Use the platform locale for day-of-week labels — defers to the
  // user's preference (so a French parent sees lun mar mer ...).
  // Two-character labels keep the cell header compact; format short
  // returns "Mo Tu We" in en-US which is fine.
  const formatter = new Intl.DateTimeFormat(undefined, { weekday: 'short' })
  // Pick a known Sunday (1970-01-04) as anchor and walk forward.
  const anchor = new Date(1970, 0, 4) // Sunday
  const labels: string[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(anchor)
    d.setDate(d.getDate() + i + (weekStartsOn === 1 ? 1 : 0))
    labels.push(formatter.format(d))
  }
  return labels
}
