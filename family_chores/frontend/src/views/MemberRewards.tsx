import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { APIError } from '../api/client'
import {
  useCreateRedemption,
  useMember,
  useMemberRedemptions,
  useRewards,
} from '../api/hooks'
import { useKidPinStore } from '../store/kidPin'
import { PinPad } from '../components/PinPad'
import { useVerifyMemberPin } from '../api/hooks'
import { fireConfetti } from '../components/Confetti'
import type { Reward } from '../api/types'

/**
 * Kid-facing rewards catalog (DECISIONS §17 sibling feature). Shows the
 * active rewards as tap targets with cost + an explicit "X points left
 * after" preview before committing the redemption. Same per-kid PIN
 * gate as MemberView — if the member has a PIN set and the unlock has
 * lapsed, the page renders the PinPad instead.
 */
export function MemberRewards() {
  const { slug = '' } = useParams()
  const member = useMember(slug)
  const rewards = useRewards()
  const history = useMemberRedemptions(slug)
  const redeem = useCreateRedemption(slug)

  // Per-kid PIN gate (same as MemberView).
  const isUnlocked = useKidPinStore((s) => s.isUnlocked)
  const setUnlocked = useKidPinStore((s) => s.setUnlocked)
  const verifyPin = useVerifyMemberPin(slug)
  const [pinError, setPinError] = useState<string | null>(null)

  const [confirming, setConfirming] = useState<Reward | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [justRedeemed, setJustRedeemed] = useState<string | null>(null)

  if (member.isLoading || rewards.isLoading) {
    return <p className="text-brand-700">Loading…</p>
  }
  if (!member.data) {
    return <p className="text-rose-700 font-semibold">Couldn't load this member.</p>
  }

  const m = member.data

  if (m.pin_set && !isUnlocked(m.id)) {
    return (
      <div
        className="mx-auto max-w-lg pt-10"
        style={{ ['--accent' as string]: m.color }}
      >
        <div className="flex items-center gap-3 mb-6">
          <Link
            to={`/member/${slug}`}
            className="min-h-touch min-w-touch px-5 rounded-2xl font-bold bg-brand-50 text-brand-700 grid place-items-center"
          >
            ← Back
          </Link>
          <div className="text-fluid-xl font-black flex items-center gap-2">
            <span aria-hidden>{m.avatar ?? '🧒'}</span>
            <span>{m.name}'s rewards</span>
          </div>
        </div>
        <p className="text-fluid-sm text-brand-700/80 mb-4">
          Tap the digits to unlock {m.name}'s rewards.
        </p>
        <PinPad
          length={4}
          error={pinError}
          disabled={verifyPin.isPending}
          onComplete={(pin) => {
            setPinError(null)
            verifyPin.mutate(pin, {
              onSuccess: (data) => setUnlocked(m.id, data.verified_until),
              onError: () => setPinError('Wrong PIN — try again.'),
            })
          }}
        />
      </div>
    )
  }

  const balance = m.stats.points_total
  const catalog = (rewards.data ?? []).filter((r) => r.active)

  const handleRedeem = (reward: Reward) => {
    setError(null)
    redeem.mutate(
      { reward_id: reward.id },
      {
        onSuccess: () => {
          setConfirming(null)
          setJustRedeemed(reward.name)
          fireConfetti({ accent: m.color })
          // Clear the toast after 4 seconds.
          window.setTimeout(() => setJustRedeemed(null), 4000)
        },
        onError: (e) => {
          setError(
            e instanceof APIError
              ? e.detail
              : 'Could not redeem — try again later.',
          )
        },
      },
    )
  }

  return (
    <div
      className="mx-auto max-w-5xl"
      style={{ ['--accent' as string]: m.color }}
    >
      <div className="flex items-center gap-4 mb-6 flex-wrap">
        <Link
          to={`/member/${slug}`}
          className="min-h-touch min-w-touch px-5 rounded-2xl font-bold bg-brand-50 text-brand-700 grid place-items-center"
        >
          ← Chores
        </Link>
        <div className="themed-soft rounded-xl4 px-6 py-4 flex-1 flex items-center gap-4 shadow-card">
          <span className="text-fluid-2xl" aria-hidden>
            🎁
          </span>
          <div className="min-w-0">
            <div className="text-fluid-xl font-black truncate">
              {m.name}'s rewards
            </div>
            <div className="text-fluid-sm font-semibold opacity-80">
              ⭐ {balance} points to spend
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-2xl bg-rose-50 text-rose-700 font-semibold px-5 py-3"
        >
          {error}
        </div>
      )}

      {justRedeemed && (
        <div
          role="status"
          className="mb-4 rounded-2xl bg-emerald-50 text-emerald-900 font-semibold px-5 py-3"
        >
          🎉 Redeemed "{justRedeemed}" — waiting for parent approval.
        </div>
      )}

      {catalog.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-fluid-3xl" aria-hidden>
            ✨
          </div>
          <div className="mt-4 text-fluid-xl font-black text-brand-900">
            No rewards yet
          </div>
          <div className="mt-2 text-fluid-sm text-brand-700/70">
            Ask a parent to add some in Parent Mode → Rewards.
          </div>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {catalog.map((r) => {
            const affordable = balance >= r.cost_points
            return (
              <button
                key={r.id}
                type="button"
                disabled={!affordable || redeem.isPending}
                onClick={() => setConfirming(r)}
                className={
                  'rounded-xl4 bg-white p-5 shadow-card flex flex-col gap-2 text-left transition disabled:opacity-50 disabled:cursor-not-allowed enabled:hover:shadow-pop ' +
                  (!affordable ? 'border-2 border-dashed border-brand-100' : '')
                }
              >
                <div className="text-fluid-2xl" aria-hidden>
                  🎁
                </div>
                <div className="text-fluid-lg font-black text-brand-900">
                  {r.name}
                </div>
                {r.description && (
                  <div className="text-fluid-sm text-brand-700/70">
                    {r.description}
                  </div>
                )}
                <div className="mt-auto flex items-center justify-between">
                  <span className="font-black text-fluid-base">
                    ⭐ {r.cost_points}
                  </span>
                  {!affordable && (
                    <span className="text-fluid-xs font-semibold text-brand-700/70">
                      Need {r.cost_points - balance} more
                    </span>
                  )}
                </div>
              </button>
            )
          })}
        </div>
      )}

      {confirming && (
        <RedeemConfirmModal
          reward={confirming}
          balance={balance}
          memberColor={m.color}
          isPending={redeem.isPending}
          onConfirm={() => handleRedeem(confirming)}
          onCancel={() => setConfirming(null)}
        />
      )}

      {history.data && history.data.length > 0 && (
        <RecentRedemptions redemptions={history.data.slice(0, 5)} />
      )}
    </div>
  )
}

function RedeemConfirmModal({
  reward,
  balance,
  memberColor,
  isPending,
  onConfirm,
  onCancel,
}: {
  reward: Reward
  balance: number
  memberColor: string
  isPending: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const after = Math.max(0, balance - reward.cost_points)
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Confirm redemption"
    >
      <div
        className="bg-white rounded-xl4 shadow-pop max-w-md w-full p-6 space-y-4"
        style={{ borderTop: '6px solid ' + memberColor }}
      >
        <div className="text-fluid-2xl text-center" aria-hidden>
          🎁
        </div>
        <div className="text-fluid-xl font-black text-center text-brand-900">
          {reward.name}
        </div>
        {reward.description && (
          <div className="text-fluid-sm text-brand-700/80 text-center">
            {reward.description}
          </div>
        )}
        <div className="rounded-2xl bg-brand-50 px-5 py-4 space-y-1">
          <div className="flex justify-between text-fluid-sm">
            <span>You have</span>
            <span className="font-black">⭐ {balance}</span>
          </div>
          <div className="flex justify-between text-fluid-sm">
            <span>This costs</span>
            <span className="font-black">− ⭐ {reward.cost_points}</span>
          </div>
          <div className="flex justify-between text-fluid-base font-black border-t border-brand-100 pt-2 mt-2">
            <span>You'll have</span>
            <span>⭐ {after}</span>
          </div>
        </div>
        <div className="flex gap-3 justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="min-h-touch px-5 rounded-2xl font-bold text-fluid-base bg-brand-50 text-brand-700"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="min-h-touch px-6 rounded-2xl font-black text-fluid-base bg-brand-600 text-white disabled:opacity-50"
          >
            {isPending ? 'Sending…' : 'Yes, redeem'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RecentRedemptions({
  redemptions,
}: {
  redemptions: ReturnType<typeof useMemberRedemptions>['data'] extends infer T
    ? T extends Array<infer R>
      ? R[]
      : never
    : never
}) {
  return (
    <section className="mt-8">
      <h2 className="text-fluid-lg font-black text-brand-900 mb-3">
        Recent
      </h2>
      <ul className="space-y-2">
        {redemptions.map((r) => {
          const stateLabel =
            r.state === 'pending_approval'
              ? '⏳ Waiting'
              : r.state === 'approved'
                ? '✅ Approved'
                : '❌ Denied'
          return (
            <li
              key={r.id}
              className="rounded-xl bg-white px-4 py-3 shadow-card flex items-center gap-3"
            >
              <span className="text-fluid-base" aria-hidden>
                🎁
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-fluid-sm font-bold text-brand-900 truncate">
                  {r.reward_name_at_redeem}
                </div>
                <div className="text-fluid-xs text-brand-700/70">
                  ⭐ {r.cost_points_at_redeem} · {stateLabel}
                  {r.state === 'denied' && r.denied_reason && (
                    <> · {r.denied_reason}</>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
