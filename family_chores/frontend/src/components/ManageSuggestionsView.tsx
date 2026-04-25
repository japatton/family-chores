import { useState } from 'react'
import type { Suggestion, SuggestionUpdate } from '../api/types'

/**
 * Manage Suggestions view (DECISIONS §13 §6.3).
 *
 * Reached from the "Manage my suggestions" link in the Browse Suggestions
 * panel. Lists custom suggestions (parent-created) with Edit + Delete,
 * and starter suggestions in a collapsed section with Delete only
 * (starters' names are immutable per §1.2). A quiet "Reset starter
 * suggestions" link at the bottom calls the reset endpoint after a
 * confirmation.
 *
 * Pure-display: receives the suggestion list and per-action callbacks.
 * The parent (ChoresTab) wires the actual mutation hooks. Keeps this
 * component testable without a TanStack-Query provider tree.
 *
 * Plain by design — the prompt was explicit: no charts, no counts, no
 * analytics. Parents come here to delete one thing and leave.
 */

export interface ManageSuggestionsViewProps {
  suggestions: Suggestion[]
  onUpdate: (id: string, body: SuggestionUpdate) => Promise<unknown>
  onDelete: (suggestion: Suggestion) => Promise<unknown>
  onReset: () => Promise<{ suppressions_cleared: number; seeded: number }>
  onBack: () => void
}

interface DraftEdit {
  id: string
  name: string
  points_suggested: number
  description: string
  icon: string
}

function toDraft(s: Suggestion): DraftEdit {
  return {
    id: s.id,
    name: s.name,
    points_suggested: s.points_suggested,
    description: s.description ?? '',
    icon: s.icon ?? '',
  }
}

export function ManageSuggestionsView({
  suggestions,
  onUpdate,
  onDelete,
  onReset,
  onBack,
}: ManageSuggestionsViewProps) {
  const [editing, setEditing] = useState<DraftEdit | null>(null)
  const [showStarter, setShowStarter] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const customs = suggestions.filter((s) => s.source === 'custom')
  const starters = suggestions.filter((s) => s.source === 'starter')

  const handleSave = async () => {
    if (editing === null) return
    setError(null)
    setBusy(true)
    try {
      await onUpdate(editing.id, {
        name: editing.name,
        points_suggested: editing.points_suggested,
        description: editing.description || null,
        icon: editing.icon || null,
      })
      setEditing(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed.')
    } finally {
      setBusy(false)
    }
  }

  const handleDelete = async (s: Suggestion) => {
    const message =
      s.source === 'starter'
        ? `Hide "${s.name}"? You can restore it later from "Reset starter suggestions" below.`
        : `Delete "${s.name}"?`
    if (!confirm(message)) return
    setError(null)
    try {
      await onDelete(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed.')
    }
  }

  const handleReset = async () => {
    if (
      !confirm(
        'Restore starter suggestions you’ve deleted? Your custom suggestions are not affected.',
      )
    )
      return
    setError(null)
    try {
      await onReset()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reset failed.')
    }
  }

  return (
    <div
      className="rounded-xl bg-brand-50/60 p-4 space-y-4"
      data-testid="manage-suggestions-view"
    >
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h3 className="text-fluid-base font-black text-brand-900 m-0">
          Manage suggestions
        </h3>
        <button
          type="button"
          onClick={onBack}
          className="min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-white text-brand-700 border border-brand-100"
        >
          ← Back to browse
        </button>
      </div>

      {error && (
        <div role="alert" className="text-rose-600 text-fluid-sm font-semibold">
          {error}
        </div>
      )}

      {/* ─── custom (your) suggestions ───────────────────────────────────── */}
      <section className="space-y-2">
        <h4 className="text-fluid-sm font-bold text-brand-700/80 m-0">
          Your suggestions
        </h4>
        {customs.length === 0 ? (
          <p className="text-fluid-sm text-brand-700/70">
            You haven’t created any custom suggestions yet. New chores save as
            suggestions automatically (uncheck the box on the Add chore form to
            skip).
          </p>
        ) : (
          <ul className="space-y-2">
            {customs.map((s) => {
              const isEditing = editing?.id === s.id
              return (
                <li key={s.id}>
                  <div className="rounded-xl bg-white p-3 space-y-2">
                    {isEditing ? (
                      <div className="space-y-2" data-testid={`edit-${s.id}`}>
                        <label className="flex flex-col gap-1">
                          <span className="text-fluid-xs font-bold text-brand-700">
                            Name
                          </span>
                          <input
                            value={editing.name}
                            onChange={(e) =>
                              setEditing({ ...editing, name: e.target.value })
                            }
                            className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-sm"
                          />
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                          <label className="flex flex-col gap-1">
                            <span className="text-fluid-xs font-bold text-brand-700">
                              Points
                            </span>
                            <input
                              type="number"
                              min={0}
                              value={editing.points_suggested}
                              onChange={(e) =>
                                setEditing({
                                  ...editing,
                                  points_suggested:
                                    Number.parseInt(e.target.value, 10) || 0,
                                })
                              }
                              className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-sm"
                            />
                          </label>
                          <label className="flex flex-col gap-1">
                            <span className="text-fluid-xs font-bold text-brand-700">
                              Icon
                            </span>
                            <input
                              value={editing.icon}
                              onChange={(e) =>
                                setEditing({ ...editing, icon: e.target.value })
                              }
                              className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-sm"
                            />
                          </label>
                        </div>
                        <label className="flex flex-col gap-1">
                          <span className="text-fluid-xs font-bold text-brand-700">
                            Description
                          </span>
                          <input
                            value={editing.description}
                            onChange={(e) =>
                              setEditing({
                                ...editing,
                                description: e.target.value,
                              })
                            }
                            className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-sm"
                          />
                        </label>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={handleSave}
                            disabled={busy}
                            className="min-h-touch px-4 rounded-2xl bg-brand-600 text-white font-bold text-fluid-sm disabled:opacity-50"
                          >
                            {busy ? 'Saving…' : 'Save'}
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditing(null)}
                            disabled={busy}
                            className="min-h-touch px-4 rounded-2xl bg-white text-brand-700 border border-brand-100 font-bold text-fluid-sm"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="text-fluid-lg" aria-hidden>
                          {s.icon ? '✨' : '·'}
                        </span>
                        <div className="flex-1 min-w-0">
                          <div className="text-fluid-sm font-bold text-brand-900 truncate">
                            {s.name}
                          </div>
                          <div className="text-fluid-xs text-brand-700/70">
                            {s.points_suggested} pt
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => setEditing(toDraft(s))}
                          className="min-h-touch px-3 rounded-2xl font-bold text-fluid-xs bg-white text-brand-700 border border-brand-100"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(s)}
                          className="min-h-touch px-3 rounded-2xl font-bold text-fluid-xs bg-rose-50 text-rose-700"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {/* ─── starter suggestions (collapsed) ─────────────────────────────── */}
      <details
        open={showStarter}
        onToggle={(e) =>
          setShowStarter((e.target as HTMLDetailsElement).open)
        }
      >
        <summary className="cursor-pointer text-fluid-sm font-bold text-brand-700/80">
          Starter suggestions ({starters.length})
        </summary>
        <ul className="space-y-1 mt-2">
          {starters.map((s) => (
            <li key={s.id}>
              <div className="rounded-xl bg-white p-2 flex items-center gap-3">
                <span className="text-fluid-base" aria-hidden>
                  {s.icon ? '✨' : '·'}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="text-fluid-sm font-bold text-brand-900 truncate">
                    {s.name}
                  </div>
                  <div className="text-fluid-xs text-brand-700/70">
                    {s.points_suggested} pt · starter
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleDelete(s)}
                  className="min-h-touch px-3 rounded-2xl font-bold text-fluid-xs bg-rose-50 text-rose-700"
                >
                  Hide
                </button>
              </div>
            </li>
          ))}
        </ul>
      </details>

      {/* ─── reset escape hatch ──────────────────────────────────────────── */}
      <div className="text-right">
        <button
          type="button"
          onClick={handleReset}
          className="text-fluid-xs text-brand-700/80 underline"
        >
          Reset starter suggestions
        </button>
      </div>
    </div>
  )
}
