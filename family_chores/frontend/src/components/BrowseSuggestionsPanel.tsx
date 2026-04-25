import { useMemo, useState } from 'react'
import type { Suggestion, SuggestionSource } from '../api/types'

/**
 * Pure-display Browse Suggestions panel — receives the full set of
 * `suggestions` from the parent and filters in-memory. Tapping a row
 * calls `onSelect(suggestion)`; the parent does the form pre-fill.
 *
 * No data fetching here on purpose: keeps the component testable
 * without TanStack Query plumbing and lets the parent decide when to
 * lazy-load (the panel is only rendered after the "💡 Browse
 * suggestions" link is tapped).
 *
 * Naming note (DECISIONS §13 §1.2): the parent UI says "suggestions",
 * never "templates". `Suggestion` is the parent-facing word.
 */

const CATEGORY_LABELS: Record<string, string> = {
  bedroom: 'Bedroom',
  bathroom: 'Bathroom',
  kitchen: 'Kitchen',
  laundry: 'Laundry',
  pet_care: 'Pet care',
  outdoor: 'Outdoor',
  personal_care: 'Personal care',
  schoolwork: 'Schoolwork',
  tidying: 'Tidying',
  meals: 'Meals',
  other: 'Other',
}

const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS)

export interface BrowseSuggestionsPanelProps {
  suggestions: Suggestion[]
  onSelect: (suggestion: Suggestion) => void
  onManage?: () => void
  /** Useful for tests / future first-run nudges to seed initial state. */
  initialAge?: number | null
}

export function BrowseSuggestionsPanel({
  suggestions,
  onSelect,
  onManage,
  initialAge = null,
}: BrowseSuggestionsPanelProps) {
  const [search, setSearch] = useState('')
  const [activeCategories, setActiveCategories] = useState<string[]>([])
  const [age, setAge] = useState<number | null>(initialAge)
  const [source, setSource] = useState<'all' | SuggestionSource>('all')
  const [showSourceFilter, setShowSourceFilter] = useState(false)

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return suggestions.filter((s) => {
      if (needle && !s.name.toLowerCase().includes(needle)) return false
      if (activeCategories.length > 0) {
        if (s.category == null || !activeCategories.includes(s.category)) {
          return false
        }
      }
      if (age !== null) {
        if (s.age_min != null && s.age_min > age) return false
        if (s.age_max != null && s.age_max < age) return false
      }
      if (source !== 'all' && s.source !== source) return false
      return true
    })
  }, [suggestions, search, activeCategories, age, source])

  const grouped = useMemo(() => {
    const out: Array<{ category: string; items: Suggestion[] }> = []
    const buckets = new Map<string, Suggestion[]>()
    for (const s of filtered) {
      const cat = s.category ?? 'other'
      const arr = buckets.get(cat) ?? []
      arr.push(s)
      buckets.set(cat, arr)
    }
    // Stable category order from CATEGORY_ORDER, then any unknown ones.
    for (const cat of CATEGORY_ORDER) {
      const items = buckets.get(cat)
      if (items && items.length > 0) {
        out.push({ category: cat, items })
        buckets.delete(cat)
      }
    }
    for (const [cat, items] of buckets.entries()) {
      out.push({ category: cat, items })
    }
    return out
  }, [filtered])

  const toggleCategory = (cat: string) => {
    setActiveCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat],
    )
  }

  return (
    <div
      className="rounded-xl bg-brand-50/60 p-4 space-y-3"
      data-testid="browse-suggestions-panel"
    >
      <div className="flex items-center gap-2">
        <input
          type="search"
          placeholder="Search suggestions"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 rounded-xl border border-brand-100 bg-white px-3 py-2 text-fluid-sm"
          aria-label="Search suggestions"
        />
        <label className="flex items-center gap-2 text-fluid-xs text-brand-700">
          <span className="font-bold">Age</span>
          <input
            type="number"
            min={2}
            max={18}
            value={age ?? ''}
            placeholder="any"
            onChange={(e) => {
              const v = e.target.value
              setAge(v === '' ? null : Number.parseInt(v, 10))
            }}
            className="w-16 rounded-xl border border-brand-100 bg-white px-2 py-2 text-fluid-sm"
            aria-label="Filter by age"
          />
          {age !== null && (
            <button
              type="button"
              onClick={() => setAge(null)}
              className="text-brand-700/70 underline text-fluid-xs"
            >
              clear
            </button>
          )}
        </label>
      </div>

      <div className="flex flex-wrap gap-2">
        {CATEGORY_ORDER.map((cat) => {
          const on = activeCategories.includes(cat)
          return (
            <button
              key={cat}
              type="button"
              onClick={() => toggleCategory(cat)}
              className={
                'min-h-[2.25rem] px-3 rounded-2xl font-bold text-fluid-xs ' +
                (on
                  ? 'bg-brand-600 text-white'
                  : 'bg-white text-brand-700 border border-brand-100')
              }
              aria-pressed={on}
            >
              {CATEGORY_LABELS[cat]}
            </button>
          )
        })}
      </div>

      <details
        open={showSourceFilter}
        onToggle={(e) =>
          setShowSourceFilter((e.target as HTMLDetailsElement).open)
        }
      >
        <summary className="cursor-pointer text-fluid-xs font-bold text-brand-700/80">
          Filter by source
        </summary>
        <div className="mt-2 flex gap-2">
          {(['all', 'starter', 'custom'] as const).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setSource(v)}
              aria-pressed={source === v}
              className={
                'min-h-[2rem] px-3 rounded-2xl font-semibold text-fluid-xs ' +
                (source === v
                  ? 'bg-brand-600 text-white'
                  : 'bg-white text-brand-700 border border-brand-100')
              }
            >
              {v === 'all'
                ? 'All suggestions'
                : v === 'starter'
                  ? 'Starter only'
                  : 'My suggestions only'}
            </button>
          ))}
        </div>
      </details>

      {grouped.length === 0 ? (
        <p className="text-fluid-sm text-brand-700/70" role="status">
          No suggestions match these filters.
        </p>
      ) : (
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {grouped.map(({ category, items }) => (
            <div key={category} className="space-y-1">
              <h3 className="text-fluid-xs font-bold text-brand-700/80 uppercase tracking-wide m-0">
                {CATEGORY_LABELS[category] ?? category}
              </h3>
              <ul className="space-y-1">
                {items.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(s)}
                      className="w-full text-left rounded-xl bg-white px-3 py-2 flex items-center gap-3 hover:bg-brand-100 focus:bg-brand-100 transition-colors"
                      data-testid={`suggestion-${s.id}`}
                    >
                      <span className="text-fluid-lg" aria-hidden>
                        {s.icon ? '✨' : '·'}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="block text-fluid-sm font-bold text-brand-900 truncate">
                          {s.name}
                        </span>
                        <span className="block text-fluid-xs text-brand-700/70">
                          {s.points_suggested} pt
                          {s.age_min !== null && ` · age ${s.age_min}+`}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {onManage && (
        <div className="text-right">
          <button
            type="button"
            onClick={onManage}
            className="text-fluid-xs text-brand-700/80 underline"
          >
            Manage my suggestions
          </button>
        </div>
      )}
    </div>
  )
}
