import { useState } from 'react'

interface CalendarEntityIdsEditorProps {
  value: string[]
  onChange: (value: string[]) => void
  /** Visible label above the chip strip. */
  label?: string
  /** Helper text under the input. */
  hint?: string
  /** Optional className for the outer wrapper. */
  className?: string
  /** Disable the input (e.g. while a save is in flight). */
  disabled?: boolean
}

/**
 * Chip-style editor for a list of HA `calendar.*` entity ids
 * (DECISIONS §14 PR-C). Used by both the household-shared settings
 * panel and the per-member calendar mapping in MembersTab.
 *
 * Add: type an entity id and press Enter (or click "Add"). Remove:
 * tap the × on the chip. Validation is permissive on input (only
 * "calendar." prefix is enforced — the backend re-validates on PUT)
 * to keep the input fast; full HA-side validation happens on the
 * next refresh.
 */
export function CalendarEntityIdsEditor({
  value,
  onChange,
  label,
  hint,
  className = '',
  disabled = false,
}: CalendarEntityIdsEditorProps) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)

  const submit = () => {
    const cleaned = draft.trim()
    if (!cleaned) {
      setError(null)
      return
    }
    if (!cleaned.startsWith('calendar.')) {
      setError("Entity id must start with 'calendar.'")
      return
    }
    if (value.includes(cleaned)) {
      setError('Already in the list')
      return
    }
    onChange([...value, cleaned])
    setDraft('')
    setError(null)
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {label && (
        <span className="text-fluid-xs font-bold text-brand-700">{label}</span>
      )}
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label="Selected calendar entities">
          {value.map((entityId) => (
            <li
              key={entityId}
              className="inline-flex items-center gap-2 rounded-full bg-brand-100 pl-3 pr-1.5 py-1 text-fluid-xs font-bold text-brand-900"
            >
              <span className="font-mono">{entityId}</span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(value.filter((v) => v !== entityId))}
                className="grid place-items-center size-6 rounded-full bg-white/70 text-brand-700 hover:bg-white disabled:opacity-50"
                aria-label={`Remove ${entityId}`}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap items-stretch gap-2">
        <input
          className="flex-1 min-w-[12rem] rounded-xl border border-brand-100 px-4 py-2.5 text-fluid-sm font-mono"
          placeholder="calendar.alice_school"
          value={draft}
          disabled={disabled}
          onChange={(e) => {
            setDraft(e.target.value)
            if (error) setError(null)
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              submit()
            }
          }}
        />
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !draft.trim()}
          className="min-h-touch px-5 rounded-2xl bg-brand-600 text-white font-black text-fluid-sm disabled:opacity-50"
        >
          Add
        </button>
      </div>
      {error && (
        <div role="alert" className="text-rose-600 text-fluid-xs font-semibold">
          {error}
        </div>
      )}
      {hint && !error && (
        <p className="text-fluid-xs text-brand-700/70">{hint}</p>
      )}
    </div>
  )
}
