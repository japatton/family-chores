import { useEffect, useState } from 'react'
import { APIError } from '../../api/client'
import {
  useChores,
  useCreateChore,
  useDeleteChore,
  useDeleteSuggestion,
  useMembers,
  useResetSuggestions,
  useSuggestions,
  useUpdateSuggestion,
} from '../../api/hooks'
import type {
  ChoreCreate,
  RecurrenceType,
  Suggestion,
  SuggestionUpdate,
} from '../../api/types'
import { BrowseSuggestionsPanel } from '../../components/BrowseSuggestionsPanel'
import { ManageSuggestionsView } from '../../components/ManageSuggestionsView'
import { useFirstRunBadge } from '../../hooks/useFirstRunBadge'

// Per-device localStorage key for the "✨ New" badge on Browse Suggestions
// (DECISIONS §13 §6.2). app_config-backed persistence is mentioned in the
// spec but deferred to v2 — see `useFirstRunBadge` for the rationale.
const SUGGESTIONS_BADGE_KEY = 'fc.suggestionsBadgeSeen'

const RECURRENCE_OPTIONS: { value: RecurrenceType; label: string }[] = [
  { value: 'daily', label: 'Every day' },
  { value: 'weekdays', label: 'Weekdays' },
  { value: 'weekends', label: 'Weekends' },
  { value: 'specific_days', label: 'Specific days' },
  { value: 'every_n_days', label: 'Every N days' },
  { value: 'monthly_on_date', label: 'Monthly on date' },
  { value: 'once', label: 'Once' },
]

const WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function ChoresTab() {
  const chores = useChores()
  const members = useMembers()
  const create = useCreateChore()
  const del = useDeleteChore()

  const [draft, setDraft] = useState<ChoreCreate>({
    name: '',
    points: 5,
    recurrence_type: 'daily',
    recurrence_config: {},
    assigned_member_ids: [],
    active: true,
  })
  const [specificDays, setSpecificDays] = useState<number[]>([])
  const [everyN, setEveryN] = useState('2')
  const [everyAnchor, setEveryAnchor] = useState(
    new Date().toISOString().slice(0, 10),
  )
  const [monthDay, setMonthDay] = useState('15')
  const [onceDate, setOnceDate] = useState(
    new Date().toISOString().slice(0, 10),
  )
  const [error, setError] = useState<string | null>(null)

  // Suggestions panel state — three modes: closed, "browse" (default
  // when opened), or "manage" (the secondary view reached from the
  // "Manage my suggestions" link in the browse panel). Lazy-loaded —
  // useSuggestions only fires when the panel is open.
  const [panelMode, setPanelMode] = useState<'closed' | 'browse' | 'manage'>(
    'closed',
  )
  const panelOpen = panelMode !== 'closed'
  const suggestions = useSuggestions(undefined, { enabled: panelOpen })
  const updateSuggestion = useUpdateSuggestion()
  const deleteSuggestion = useDeleteSuggestion()
  const resetSuggestions = useResetSuggestions()
  const [showBadge, dismissBadge] = useFirstRunBadge(SUGGESTIONS_BADGE_KEY)

  // Save-as-suggestion checkbox (DECISIONS §13 §6.1) — default checked.
  // The flag flows through to the chore POST body; the backend silently
  // dedups against existing same-name templates, returning
  // template_created=true only when a brand-new one was added alongside.
  const [saveAsSuggestion, setSaveAsSuggestion] = useState(true)
  // One-shot confirmation surfaced when the POST flag actually produced
  // a new suggestion. Cleared after 4 seconds so the form doesn't carry
  // stale messaging into the next chore the parent adds.
  const [savedMessage, setSavedMessage] = useState<string | null>(null)
  useEffect(() => {
    if (savedMessage === null) return
    const t = window.setTimeout(() => setSavedMessage(null), 4000)
    return () => window.clearTimeout(t)
  }, [savedMessage])

  if (chores.isLoading || members.isLoading) {
    return <p className="text-brand-700">Loading…</p>
  }

  const buildRecurrenceConfig = (): Record<string, unknown> => {
    switch (draft.recurrence_type) {
      case 'specific_days':
        return { days: specificDays }
      case 'every_n_days':
        return { n: Number.parseInt(everyN, 10) || 1, anchor: everyAnchor }
      case 'monthly_on_date':
        return { day: Number.parseInt(monthDay, 10) || 1 }
      case 'once':
        return { date: onceDate }
      default:
        return {}
    }
  }

  /**
   * Pre-fill every form field from a suggestion. Pulls the per-recurrence-
   * type state out of `default_recurrence_config` so the right secondary
   * controls populate too. Closes the panel afterwards (DECISIONS §13 §6.1).
   */
  const applySuggestion = (s: Suggestion) => {
    const cfg = s.default_recurrence_config as Record<string, unknown>
    setDraft({
      name: s.name,
      icon: s.icon,
      points: s.points_suggested,
      description: s.description,
      recurrence_type: s.default_recurrence_type,
      recurrence_config: cfg,
      assigned_member_ids: draft.assigned_member_ids ?? [],
      active: true,
      template_id: s.id,
    })
    if (s.default_recurrence_type === 'specific_days' && Array.isArray(cfg.days)) {
      setSpecificDays((cfg.days as number[]).slice())
    }
    if (s.default_recurrence_type === 'every_n_days') {
      if (typeof cfg.n === 'number') setEveryN(String(cfg.n))
      if (typeof cfg.anchor === 'string') setEveryAnchor(cfg.anchor)
    }
    if (s.default_recurrence_type === 'monthly_on_date' && typeof cfg.day === 'number') {
      setMonthDay(String(cfg.day))
    }
    if (s.default_recurrence_type === 'once' && typeof cfg.date === 'string') {
      setOnceDate(cfg.date)
    }
    setPanelMode('closed')
    setError(null)
  }

  const submit = () => {
    setError(null)
    if (!draft.name.trim()) {
      setError('Name is required.')
      return
    }
    const body: ChoreCreate = {
      ...draft,
      recurrence_config: buildRecurrenceConfig(),
      save_as_suggestion: saveAsSuggestion,
    }
    const choreName = body.name
    create.mutate(body, {
      onSuccess: (result) => {
        setDraft({
          name: '',
          points: 5,
          recurrence_type: 'daily',
          recurrence_config: {},
          assigned_member_ids: [],
          active: true,
        })
        setSpecificDays([])
        setSaveAsSuggestion(true)
        if (result.template_created) {
          setSavedMessage(
            `Saved "${choreName}" as a suggestion for next time.`,
          )
        } else {
          setSavedMessage(null)
        }
      },
      onError: (e) => {
        if (e instanceof APIError) setError(e.detail)
      },
    })
  }

  return (
    <div className="space-y-6">
      <ul className="space-y-3">
        {(chores.data ?? []).map((c) => {
          const assigned = (members.data ?? []).filter((m) =>
            c.assigned_member_ids.includes(m.id),
          )
          return (
            <li
              key={c.id}
              className="rounded-xl4 bg-white p-5 shadow-card flex items-center gap-4 flex-wrap"
            >
              <span className="text-fluid-xl" aria-hidden>
                {c.icon ?? '✨'}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-fluid-lg font-black truncate">{c.name}</div>
                <div className="text-fluid-xs font-semibold text-brand-700/80">
                  {c.points} pt · {c.recurrence_type} ·{' '}
                  {assigned.length > 0
                    ? assigned.map((m) => m.name).join(', ')
                    : 'nobody assigned'}
                  {!c.active && ' · inactive'}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (confirm(`Delete "${c.name}"?`)) {
                    del.mutate(c.id)
                  }
                }}
                className="min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-rose-50 text-rose-700"
              >
                Delete
              </button>
            </li>
          )
        })}
      </ul>

      <div className="rounded-xl4 bg-white p-5 shadow-card space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="text-fluid-base font-black text-brand-900">Add a chore</div>
          <button
            type="button"
            onClick={() => {
              setPanelMode((m) => (m === 'closed' ? 'browse' : 'closed'))
              // Discoverability badge is one-shot — dismiss as soon as
              // the parent acknowledges the affordance, regardless of
              // whether they kept the panel open or immediately closed
              // it. See DECISIONS §13 §1.3.
              if (showBadge) dismissBadge()
            }}
            aria-expanded={panelOpen}
            aria-controls="browse-suggestions-region"
            className="min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-brand-50 text-brand-700 border border-brand-100 inline-flex items-center gap-2"
          >
            <span>
              💡 {panelOpen ? 'Hide suggestions' : 'Browse suggestions'}
            </span>
            {showBadge && !panelOpen && (
              <span
                data-testid="suggestions-new-badge"
                className="rounded-full bg-amber-200 text-amber-900 text-fluid-xs font-bold px-2 py-0.5"
                aria-label="new feature"
              >
                ✨ New
              </span>
            )}
          </button>
        </div>
        {panelOpen && (
          <div id="browse-suggestions-region">
            {suggestions.isLoading ? (
              <p className="text-fluid-sm text-brand-700/70">Loading suggestions…</p>
            ) : suggestions.isError ? (
              <p
                role="alert"
                className="text-fluid-sm text-rose-600 font-semibold"
              >
                Couldn’t load suggestions. {(suggestions.error as Error)?.message}
              </p>
            ) : panelMode === 'manage' ? (
              <ManageSuggestionsView
                suggestions={suggestions.data ?? []}
                onUpdate={(id, body: SuggestionUpdate) =>
                  updateSuggestion.mutateAsync({ id, body })
                }
                onDelete={(s) => deleteSuggestion.mutateAsync(s.id)}
                onReset={() => resetSuggestions.mutateAsync()}
                onBack={() => setPanelMode('browse')}
              />
            ) : (
              <BrowseSuggestionsPanel
                suggestions={suggestions.data ?? []}
                onSelect={applySuggestion}
                onManage={() => setPanelMode('manage')}
              />
            )}
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Name</span>
            <input
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Icon (emoji)</span>
            <input
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              value={draft.icon ?? ''}
              onChange={(e) => setDraft({ ...draft, icon: e.target.value || null })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Points</span>
            <input
              type="number"
              min={0}
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              value={draft.points ?? 0}
              onChange={(e) =>
                setDraft({ ...draft, points: Number.parseInt(e.target.value, 10) || 0 })
              }
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Recurrence</span>
            <select
              value={draft.recurrence_type}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  recurrence_type: e.target.value as RecurrenceType,
                })
              }
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
            >
              {RECURRENCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {draft.recurrence_type === 'specific_days' && (
          <div className="flex gap-2 flex-wrap">
            {WEEKDAY_NAMES.map((wd, idx) => {
              const iso = idx + 1
              const on = specificDays.includes(iso)
              return (
                <button
                  key={wd}
                  type="button"
                  onClick={() =>
                    setSpecificDays((days) =>
                      on ? days.filter((d) => d !== iso) : [...days, iso],
                    )
                  }
                  className={
                    'min-h-touch px-4 rounded-2xl font-bold text-fluid-sm ' +
                    (on
                      ? 'bg-brand-600 text-white'
                      : 'bg-brand-50 text-brand-700')
                  }
                >
                  {wd}
                </button>
              )
            })}
          </div>
        )}
        {draft.recurrence_type === 'every_n_days' && (
          <div className="flex gap-3 flex-wrap items-end">
            <label className="flex flex-col gap-1">
              <span className="text-fluid-xs font-bold text-brand-700">N</span>
              <input
                type="number"
                min={1}
                className="rounded-xl border border-brand-100 px-3 py-2 w-20 text-fluid-base"
                value={everyN}
                onChange={(e) => setEveryN(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-fluid-xs font-bold text-brand-700">Anchor</span>
              <input
                type="date"
                className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-base"
                value={everyAnchor}
                onChange={(e) => setEveryAnchor(e.target.value)}
              />
            </label>
          </div>
        )}
        {draft.recurrence_type === 'monthly_on_date' && (
          <label className="flex flex-col gap-1 max-w-[10rem]">
            <span className="text-fluid-xs font-bold text-brand-700">Day (1-31)</span>
            <input
              type="number"
              min={1}
              max={31}
              className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-base"
              value={monthDay}
              onChange={(e) => setMonthDay(e.target.value)}
            />
          </label>
        )}
        {draft.recurrence_type === 'once' && (
          <label className="flex flex-col gap-1 max-w-xs">
            <span className="text-fluid-xs font-bold text-brand-700">Date</span>
            <input
              type="date"
              className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-base"
              value={onceDate}
              onChange={(e) => setOnceDate(e.target.value)}
            />
          </label>
        )}

        <div>
          <div className="text-fluid-xs font-bold text-brand-700 mb-1">Assign to</div>
          <div className="flex flex-wrap gap-2">
            {(members.data ?? []).map((m) => {
              const on = (draft.assigned_member_ids ?? []).includes(m.id)
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() =>
                    setDraft({
                      ...draft,
                      assigned_member_ids: on
                        ? (draft.assigned_member_ids ?? []).filter((x) => x !== m.id)
                        : [...(draft.assigned_member_ids ?? []), m.id],
                    })
                  }
                  className={
                    'min-h-touch px-4 rounded-2xl font-bold text-fluid-sm ' +
                    (on
                      ? 'text-white'
                      : 'bg-brand-50 text-brand-700 border border-brand-100')
                  }
                  style={on ? { backgroundColor: m.color } : undefined}
                >
                  {m.avatar ?? '🧒'} {m.name}
                </button>
              )
            })}
            {(members.data ?? []).length === 0 && (
              <span className="text-fluid-sm text-brand-700/70">
                No members yet — add one first.
              </span>
            )}
          </div>
        </div>

        {error && (
          <div role="alert" className="text-rose-600 text-fluid-sm font-semibold">
            {error}
          </div>
        )}
        {savedMessage && (
          <div
            role="status"
            className="text-emerald-700 text-fluid-sm font-semibold"
          >
            {savedMessage}
          </div>
        )}

        <div className="flex items-center justify-between gap-3 flex-wrap pt-1 border-t border-brand-50">
          <label className="flex items-center gap-2 text-fluid-sm text-brand-700">
            <input
              type="checkbox"
              checked={saveAsSuggestion}
              onChange={(e) => setSaveAsSuggestion(e.target.checked)}
              className="h-5 w-5 rounded border-brand-200 accent-brand-600"
            />
            <span>💾 Save as a suggestion for later</span>
          </label>
          <button
            type="button"
            onClick={submit}
            disabled={create.isPending}
            className="min-h-touch px-6 rounded-2xl bg-brand-600 text-white font-black text-fluid-base disabled:opacity-50"
          >
            {create.isPending ? 'Saving…' : 'Add chore'}
          </button>
        </div>
      </div>
    </div>
  )
}
