import { useState } from 'react'
import { APIError } from '../../api/client'
import {
  useApproveRedemption,
  useCreateReward,
  useDeleteReward,
  useDenyRedemption,
  useMembers,
  useRedemptions,
  useRewards,
  useUpdateReward,
} from '../../api/hooks'
import type { Reward, RewardCreate, RewardUpdate } from '../../api/types'

/**
 * Parent-side rewards UI. Two stacked panels:
 *   - Pending queue at the top (high signal, time-sensitive)
 *   - Catalog CRUD below (lower-frequency parent maintenance)
 *
 * Mirrors the existing Approvals + Members shape. No new tab metadata
 * — the parent ParentView is updated separately to add the route.
 */
export function RewardsTab() {
  return (
    <div className="space-y-8">
      <PendingQueue />
      <Catalog />
    </div>
  )
}

// ─── pending queue ────────────────────────────────────────────────────────

function PendingQueue() {
  const queue = useRedemptions({ state: 'pending_approval' })
  const members = useMembers()
  const approve = useApproveRedemption()
  const deny = useDenyRedemption()
  const [denying, setDenying] = useState<string | null>(null)
  const [reason, setReason] = useState('')

  if (queue.isLoading) {
    return <p className="text-brand-700">Loading queue…</p>
  }

  const memberById = new Map((members.data ?? []).map((m) => [m.id, m]))
  const items = queue.data ?? []

  return (
    <section className="space-y-3">
      <header className="flex items-center justify-between">
        <h2 className="text-fluid-lg font-black text-brand-900">
          Pending redemptions
          {items.length > 0 && (
            <span className="ml-2 text-fluid-sm font-bold text-amber-700">
              ({items.length})
            </span>
          )}
        </h2>
      </header>

      {items.length === 0 ? (
        <p className="text-fluid-sm text-brand-700/70">
          No pending redemptions.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((r) => {
            const m = memberById.get(r.member_id)
            return (
              <li
                key={r.id}
                className="rounded-xl4 bg-white p-4 shadow-card space-y-3"
                style={
                  m
                    ? { borderLeft: '6px solid ' + m.color }
                    : undefined
                }
              >
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-fluid-xl" aria-hidden>
                    🎁
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-fluid-base font-black text-brand-900 truncate">
                      {r.reward_name_at_redeem}
                    </div>
                    <div className="text-fluid-xs font-semibold text-brand-700/80">
                      {m?.name ?? `member #${r.member_id}`} · ⭐{' '}
                      {r.cost_points_at_redeem} · requested{' '}
                      {new Date(r.requested_at).toLocaleString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={approve.isPending}
                    onClick={() => approve.mutate(r.id)}
                    className="min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-emerald-600 text-white disabled:opacity-50"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setReason('')
                      setDenying(denying === r.id ? null : r.id)
                    }}
                    className="min-h-touch px-4 rounded-2xl font-bold text-fluid-sm bg-rose-50 text-rose-700"
                  >
                    Deny
                  </button>
                </div>
                {denying === r.id && (
                  <div className="rounded-xl bg-rose-50/70 p-3 space-y-2">
                    <label className="flex flex-col gap-1">
                      <span className="text-fluid-xs font-bold text-rose-700">
                        Reason (optional, shown to {m?.name ?? 'kid'})
                      </span>
                      <input
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        className="rounded-xl border border-rose-200 px-3 py-2 text-fluid-sm bg-white"
                        placeholder="e.g. Not enough chores done this week"
                      />
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={deny.isPending}
                        onClick={() => {
                          deny.mutate(
                            { id: r.id, reason: reason || undefined },
                            {
                              onSuccess: () => {
                                setDenying(null)
                                setReason('')
                              },
                            },
                          )
                        }}
                        className="min-h-touch px-5 rounded-2xl font-bold text-fluid-sm bg-rose-600 text-white disabled:opacity-50"
                      >
                        Deny + refund
                      </button>
                      <button
                        type="button"
                        onClick={() => setDenying(null)}
                        className="min-h-touch px-5 rounded-2xl font-bold text-fluid-sm bg-white text-brand-700 border border-brand-100"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// ─── catalog CRUD ─────────────────────────────────────────────────────────

const EMPTY_DRAFT: RewardCreate = {
  name: '',
  description: null,
  cost_points: 50,
  icon: null,
  active: true,
  max_per_week: null,
}

function Catalog() {
  const rewards = useRewards({ active: undefined })
  const create = useCreateReward()
  const [draft, setDraft] = useState<RewardCreate>(EMPTY_DRAFT)
  const [error, setError] = useState<string | null>(null)

  if (rewards.isLoading) {
    return <p className="text-brand-700">Loading rewards…</p>
  }

  const submit = () => {
    setError(null)
    if (!draft.name.trim()) {
      setError('Name is required.')
      return
    }
    if (draft.cost_points < 1) {
      setError('Cost must be at least 1 point.')
      return
    }
    create.mutate(draft, {
      onSuccess: () => setDraft(EMPTY_DRAFT),
      onError: (e) => {
        if (e instanceof APIError) setError(e.detail)
      },
    })
  }

  const items = rewards.data ?? []
  const activeItems = items.filter((r) => r.active)
  const retiredItems = items.filter((r) => !r.active)

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-fluid-lg font-black text-brand-900">
          Reward catalog
        </h2>
        <p className="text-fluid-sm text-brand-700/70">
          What kids can spend their points on.
        </p>
      </header>

      <ul className="space-y-2">
        {activeItems.map((r) => (
          <RewardRow key={r.id} reward={r} />
        ))}
      </ul>

      {retiredItems.length > 0 && (
        <details>
          <summary className="cursor-pointer text-fluid-sm font-bold text-brand-700/80">
            Retired ({retiredItems.length})
          </summary>
          <ul className="space-y-2 mt-2">
            {retiredItems.map((r) => (
              <RewardRow key={r.id} reward={r} />
            ))}
          </ul>
        </details>
      )}

      <div className="rounded-xl4 bg-white p-5 shadow-card space-y-3">
        <div className="text-fluid-base font-black text-brand-900">
          Add a reward
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
            <span className="text-fluid-xs font-bold text-brand-700">Cost (points)</span>
            <input
              type="number"
              min={1}
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              value={draft.cost_points}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  cost_points: Number.parseInt(e.target.value, 10) || 1,
                })
              }
            />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className="text-fluid-xs font-bold text-brand-700">
              Description (optional)
            </span>
            <input
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              value={draft.description ?? ''}
              onChange={(e) =>
                setDraft({ ...draft, description: e.target.value || null })
              }
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">
              Max per week (optional)
            </span>
            <input
              type="number"
              min={1}
              max={100}
              className="rounded-xl border border-brand-100 px-4 py-3 text-fluid-base"
              value={draft.max_per_week ?? ''}
              placeholder="no limit"
              onChange={(e) =>
                setDraft({
                  ...draft,
                  max_per_week:
                    e.target.value === ''
                      ? null
                      : Number.parseInt(e.target.value, 10) || null,
                })
              }
            />
          </label>
        </div>
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
          {create.isPending ? 'Saving…' : 'Add reward'}
        </button>
      </div>
    </section>
  )
}

function RewardRow({ reward }: { reward: Reward }) {
  const update = useUpdateReward()
  const del = useDeleteReward()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<RewardUpdate>({})

  const submit = () => {
    update.mutate(
      { id: reward.id, body: draft },
      {
        onSuccess: () => {
          setEditing(false)
          setDraft({})
        },
      },
    )
  }

  return (
    <li
      className={
        'rounded-xl4 bg-white p-4 shadow-card space-y-2 ' +
        (reward.active ? '' : 'opacity-60')
      }
    >
      {editing ? (
        <div className="space-y-2">
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Name</span>
            <input
              defaultValue={reward.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className="rounded-xl border border-brand-100 px-3 py-2 text-fluid-sm"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-fluid-xs font-bold text-brand-700">Cost</span>
            <input
              type="number"
              min={1}
              defaultValue={reward.cost_points}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  cost_points: Number.parseInt(e.target.value, 10) || 1,
                })
              }
              className="rounded-xl border border-brand-100 px-3 py-2 w-32 text-fluid-sm"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={submit}
              disabled={update.isPending}
              className="min-h-touch px-4 rounded-2xl bg-brand-600 text-white font-bold text-fluid-sm disabled:opacity-50"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false)
                setDraft({})
              }}
              className="min-h-touch px-4 rounded-2xl bg-white text-brand-700 border border-brand-100 font-bold text-fluid-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-fluid-lg" aria-hidden>
            🎁
          </span>
          <div className="flex-1 min-w-0">
            <div className="text-fluid-sm font-bold text-brand-900 truncate">
              {reward.name}
              {!reward.active && (
                <span className="ml-2 text-fluid-xs font-semibold text-brand-700/70">
                  (retired)
                </span>
              )}
            </div>
            <div className="text-fluid-xs text-brand-700/70">
              ⭐ {reward.cost_points}
              {reward.max_per_week !== null && (
                <> · max {reward.max_per_week}/week</>
              )}
              {reward.description && <> · {reward.description}</>}
            </div>
          </div>
          {reward.active && (
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="min-h-touch px-3 rounded-2xl font-bold text-fluid-xs bg-white text-brand-700 border border-brand-100"
            >
              Edit
            </button>
          )}
          {reward.active ? (
            <button
              type="button"
              disabled={del.isPending}
              onClick={() => {
                if (confirm(`Retire "${reward.name}"? Past redemptions are kept.`)) {
                  del.mutate(reward.id)
                }
              }}
              className="min-h-touch px-3 rounded-2xl font-bold text-fluid-xs bg-rose-50 text-rose-700"
            >
              Retire
            </button>
          ) : (
            <button
              type="button"
              disabled={update.isPending}
              onClick={() =>
                update.mutate({ id: reward.id, body: { active: true } })
              }
              className="min-h-touch px-3 rounded-2xl font-bold text-fluid-xs bg-emerald-50 text-emerald-700"
            >
              Reactivate
            </button>
          )}
        </div>
      )}
    </li>
  )
}
