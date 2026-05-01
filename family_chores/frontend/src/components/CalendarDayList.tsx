import type { CalendarEvent } from '../api/types'

interface CalendarDayListProps {
  events: CalendarEvent[]
  /** Per-tile error hint surfacing entity ids the provider couldn't reach.
   * Empty array → no hint rendered. */
  unreachable?: string[]
  /** Optional className for layout integration (gap / margin). */
  className?: string
}

/**
 * "Today's events" panel for the kid's MemberView (DECISIONS §14 PR-B).
 *
 * Renders one card per event with start time, summary, and prep
 * chips. Past events are already filtered server-side (DECISIONS §14
 * Q7), so this component just maps what it's given. The empty state
 * is intentional — when nothing's on the calendar, the panel
 * collapses to a small "nothing else today" line so the chore list
 * stays the focus.
 */
export function CalendarDayList({
  events,
  unreachable = [],
  className = '',
}: CalendarDayListProps) {
  if (events.length === 0 && unreachable.length === 0) {
    // Don't render anything — the kid view just shows chores, no
    // empty placeholder. (The compact "no events today" line could
    // land in a follow-up if user testing wants it.)
    return null
  }

  return (
    <section
      className={`themed-soft rounded-xl4 p-5 sm:p-6 shadow-card ${className}`}
      aria-labelledby="today-events-heading"
    >
      <h2
        id="today-events-heading"
        className="text-fluid-lg font-black text-brand-900 mb-3 flex items-center gap-2"
      >
        <span aria-hidden>📅</span>
        <span>Today's events</span>
      </h2>

      {unreachable.length > 0 && (
        <p
          className="text-fluid-xs text-amber-800 bg-amber-100 rounded-lg px-3 py-2 mb-3 font-semibold"
          role="status"
        >
          Couldn't reach {unreachable.length === 1 ? 'a calendar' : 'some calendars'} —
          {' '}retry from settings.
        </p>
      )}

      {events.length === 0 ? (
        <p className="text-fluid-sm text-brand-700/80 font-semibold">
          Nothing else on the calendar today.
        </p>
      ) : (
        <ul className="grid gap-3">
          {events.map((event, idx) => (
            <li
              // Events have no stable id from the provider — composite
              // key from entity_id + start + summary keeps the React
              // reconciler happy across refetches.
              key={`${event.entity_id}-${event.start}-${event.summary}-${idx}`}
              className="rounded-2xl bg-white/80 px-4 py-3 sm:px-5 sm:py-4 flex items-start gap-3 sm:gap-4"
            >
              <EventTime event={event} />
              <div className="min-w-0 flex-1">
                <div className="text-fluid-base font-bold text-brand-900 truncate">
                  {event.summary}
                </div>
                {event.location && (
                  <div className="text-fluid-xs text-brand-700/80 truncate flex items-center gap-1">
                    <span aria-hidden>📍</span>
                    <span>{event.location}</span>
                  </div>
                )}
                {event.prep_items.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {event.prep_items.map((item) => (
                      <span
                        key={item.label}
                        className="inline-flex items-center gap-1.5 rounded-full bg-brand-100 px-3 py-1 text-fluid-xs font-bold text-brand-900"
                      >
                        {item.icon !== null && (
                          <span aria-hidden className="text-base leading-none">
                            {item.icon}
                          </span>
                        )}
                        <span>{item.label}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function EventTime({ event }: { event: CalendarEvent }) {
  // All-day events show a glyph instead of a clock time so they don't
  // pretend to be at midnight.
  if (event.all_day) {
    return (
      <div
        className="shrink-0 grid place-items-center w-14 sm:w-16 rounded-xl bg-brand-100 text-brand-700 font-bold text-fluid-xs px-2 py-2"
        aria-label="All day"
      >
        <span aria-hidden className="text-lg">
          ☀️
        </span>
        <span className="text-[0.7em] uppercase tracking-wide">All day</span>
      </div>
    )
  }
  const start = new Date(event.start)
  const formatter = new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  })
  const time = formatter.format(start)
  return (
    <div
      className="shrink-0 grid place-items-center min-w-[3.5rem] sm:min-w-[4rem] rounded-xl bg-brand-100 text-brand-700 font-bold text-fluid-sm px-3 py-2"
      aria-label={`Starts at ${time}`}
    >
      {time}
    </div>
  )
}
