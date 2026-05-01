import type { CalendarEvent, CalendarPrepItem } from '../api/types'

interface PrepChipStripProps {
  events: CalendarEvent[]
  /** Maximum chips to render before collapsing into a "+N more" pill.
   * Mobile-first; the parent's home tile shouldn't get cluttered. */
  maxChips?: number
  /** Optional className to thread theming/spacing from the parent. */
  className?: string
}

/**
 * Compact "what to bring today" strip for the parent's home MemberTile
 * (DECISIONS §14 PR-B). De-dupes prep items across all of today's
 * events for the member so "Bring cleats" appearing on three soccer
 * games doesn't render three identical chips.
 *
 * Renders nothing when there are no prep items — the chip strip is
 * additive; an empty calendar day is just no UI here, not a "no
 * events" placeholder (that lives in the full CalendarDayList).
 */
export function PrepChipStrip({
  events,
  maxChips = 4,
  className = '',
}: PrepChipStripProps) {
  // Collapse all today's events into a unique-by-label list of prep items.
  // Order follows first-seen (which mirrors the server's order: the
  // parent's source-text sequence). An item with an icon trumps a
  // duplicate without one — so if "lunch" appears once with 🍱 and
  // once without, the chip gets the icon.
  const seen = new Map<string, CalendarPrepItem>()
  for (const event of events) {
    for (const item of event.prep_items) {
      const key = item.label.toLowerCase()
      const existing = seen.get(key)
      if (existing === undefined) {
        seen.set(key, item)
      } else if (existing.icon === null && item.icon !== null) {
        seen.set(key, item)
      }
    }
  }
  const items = Array.from(seen.values())
  if (items.length === 0) return null

  const visible = items.slice(0, maxChips)
  const hidden = items.length - visible.length

  return (
    <div
      className={`flex flex-wrap items-center gap-2 ${className}`}
      aria-label="Things to bring today"
    >
      {visible.map((item) => (
        <span
          key={item.label}
          // Soft-on-tile chip — relies on the surrounding tile's
          // `--accent` background for contrast. White text + 20%
          // white film keeps the chip legible on any kid's accent.
          className="inline-flex items-center gap-1.5 rounded-full bg-white/20 px-3 py-1 text-fluid-xs font-bold text-white"
        >
          {item.icon !== null && (
            <span aria-hidden className="text-base leading-none">
              {item.icon}
            </span>
          )}
          <span className="truncate max-w-[8rem]">{item.label}</span>
        </span>
      ))}
      {hidden > 0 && (
        <span className="inline-flex items-center rounded-full bg-white/20 px-3 py-1 text-fluid-xs font-bold text-white">
          +{hidden} more
        </span>
      )}
    </div>
  )
}
