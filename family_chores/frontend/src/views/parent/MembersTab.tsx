import { useState } from 'react'
import { APIError } from '../../api/client'
import {
  useAdjustPoints,
  useCreateMember,
  useDeleteMember,
  useMembers,
  useUpdateMember,
} from '../../api/hooks'
import type { Member, MemberCreate } from '../../api/types'

const DEFAULT_COLORS = [
  '#6366f1',
  '#f97316',
  '#14b8a6',
  '#ec4899',
  '#eab308',
  '#22c55e',
  '#ef4444',
  '#8b5cf6',
]

export function MembersTab() {
  const members = useMembers()
  const create = useCreateMember()
  const del = useDeleteMember()

  const [draft, setDraft] = useState<MemberCreate>({
    name: '',
    slug: '',
    color: DEFAULT_COLORS[0],
    display_mode: 'kid_standard',
    requires_approval: false,
    ha_todo_entity_id: null,
  })
  const [error, setError] = useState<string | null>(null)

  if (members.isLoading) return <p className="text-brand-700">Loading…</p>

  const submit = () => {
    setError(null)
    if (!draft.name || !draft.slug) {
      setError('Name and slug are required.')
      return
    }
    create.mutate(draft, {
      onSuccess: () => {
        setDraft({
          name: '',
          slug: '',
          color: DEFAULT_COLORS[0],
          display_mode: 'kid_standard',
          requires_approval: false,
          ha_todo_entity_id: null,
        })
      },
      onError: (e) => {
        if (e instanceof APIError) setError(e.detail)
      },
    })
  }

  return (
    <div className="space-y-6">
      <ul className="space-y-3">
        {(members.data ?? []).map((m) => (
          <MemberRow
            key={m.id}
            member={m}
            onDelete={() => {
              if (confirm(`Delete ${m.name}? This removes their instances.`)) {
                del.mutate(m.slug)
              }
            }}
          />
        ))}
      </ul>

      <div className="rounded-xl4 bg-white p-5 shadow-card space-y-3">
        <div className="text-fluid-base font-black text-brand-900">
          Add a family member
        </div>
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
            <span className="text-fluid-xs font-bold text-brand-700">
              Slug (a-z, 0-9, -, _)
            </span>
            <input
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              value={draft.slug}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  slug: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''),
                })
              }
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Avatar (emoji)</span>
            <input
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              placeholder="🦸"
              value={draft.avatar ?? ''}
              onChange={(e) => setDraft({ ...draft, avatar: e.target.value || null })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">
              HA Todo entity (optional)
            </span>
            <input
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-sm font-mono"
              placeholder="todo.alice_chores"
              value={draft.ha_todo_entity_id ?? ''}
              onChange={(e) =>
                setDraft({ ...draft, ha_todo_entity_id: e.target.value || null })
              }
            />
          </label>
        </div>
        <div className="flex items-center gap-4 flex-wrap">
          <span className="text-fluid-xs font-bold text-brand-700">Color</span>
          {DEFAULT_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setDraft({ ...draft, color: c })}
              className="size-9 rounded-full border-4"
              style={{
                backgroundColor: c,
                borderColor: draft.color === c ? '#0f172a' : 'transparent',
              }}
              aria-label={`color ${c}`}
            />
          ))}
        </div>
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            className="size-6"
            checked={draft.requires_approval ?? false}
            onChange={(e) =>
              setDraft({ ...draft, requires_approval: e.target.checked })
            }
          />
          <span className="text-fluid-sm font-semibold">Requires parent approval</span>
        </label>
        {error && (
          <div role="alert" className="text-rose-600 text-fluid-sm font-semibold">
            {error}
          </div>
        )}
        <button
          type="button"
          onClick={submit}
          disabled={create.isPending}
          className="min-h-touch px-6 rounded-2xl bg-brand-600 text-white font-black text-fluid-base disabled:opacity-50"
        >
          {create.isPending ? 'Saving…' : 'Add member'}
        </button>
      </div>
    </div>
  )
}

function MemberRow({ member, onDelete }: { member: Member; onDelete: () => void }) {
  const update = useUpdateMember(member.slug)
  const adjust = useAdjustPoints()
  const [adjusting, setAdjusting] = useState(false)
  const [adjustDelta, setAdjustDelta] = useState('')
  const [adjustReason, setAdjustReason] = useState('')

  return (
    <li
      className="rounded-xl4 bg-white p-5 shadow-card flex flex-col gap-3"
      style={{ borderLeft: '6px solid ' + member.color }}
    >
      <div className="flex items-center gap-4 flex-wrap">
        <span className="text-fluid-xl" aria-hidden>
          {member.avatar ?? '🧒'}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-fluid-lg font-black truncate">{member.name}</div>
          <div className="text-fluid-xs font-semibold text-brand-700/80">
            {member.slug} · {member.stats.points_total} pts ·{' '}
            {member.stats.streak}-day streak
            {member.ha_todo_entity_id && (
              <>
                {' · '}
                <span className="font-mono">{member.ha_todo_entity_id}</span>
              </>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() =>
            update.mutate({ requires_approval: !member.requires_approval })
          }
          className={
            'min-h-touch px-4 rounded-2xl font-bold text-fluid-sm ' +
            (member.requires_approval
              ? 'bg-amber-500 text-white'
              : 'bg-brand-50 text-brand-700')
          }
        >
          {member.requires_approval
            ? '✓ Approval required'
            : 'Approval: off'}
        </button>
        <button
          type="button"
          onClick={() => setAdjusting((v) => !v)}
          className="min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-brand-50 text-brand-700"
        >
          ± points
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-rose-50 text-rose-700"
        >
          Delete
        </button>
      </div>
      {adjusting && (
        <div className="flex items-end gap-3 flex-wrap">
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Delta (±)</span>
            <input
              type="number"
              value={adjustDelta}
              onChange={(e) => setAdjustDelta(e.target.value)}
              className="rounded-xl border border-brand-100 px-3 py-2 w-28 text-fluid-base"
            />
          </label>
          <label className="flex flex-col gap-1 flex-1 min-w-[8rem]">
            <span className="text-fluid-xs font-bold text-brand-700">Reason</span>
            <input
              value={adjustReason}
              onChange={(e) => setAdjustReason(e.target.value)}
              className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-base"
            />
          </label>
          <button
            type="button"
            onClick={() => {
              const d = Number.parseInt(adjustDelta, 10)
              if (Number.isNaN(d)) return
              adjust.mutate(
                {
                  memberId: member.id,
                  delta: d,
                  reason: adjustReason || undefined,
                },
                {
                  onSuccess: () => {
                    setAdjusting(false)
                    setAdjustDelta('')
                    setAdjustReason('')
                  },
                },
              )
            }}
            disabled={adjust.isPending}
            className="min-h-touch px-5 rounded-2xl bg-brand-600 text-white font-black"
          >
            Apply
          </button>
        </div>
      )}
    </li>
  )
}
