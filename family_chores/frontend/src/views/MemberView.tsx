import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  useCompleteInstance,
  useMember,
  useToday,
  useUndoInstance,
  useVerifyMemberPin,
} from '../api/hooks'
import { CelebrationAllDone } from '../components/CelebrationAllDone'
import { ChoreCard } from '../components/ChoreCard'
import { fireConfetti } from '../components/Confetti'
import { PinPad } from '../components/PinPad'
import { UndoToast } from '../components/UndoToast'
import { useChime } from '../hooks/useChime'
import { useKidPinStore } from '../store/kidPin'

export function MemberView() {
  const { slug = '' } = useParams()
  const member = useMember(slug)
  const today = useToday()

  const complete = useCompleteInstance()
  const undo = useUndoInstance()
  const playChime = useChime()
  const [undoTarget, setUndoTarget] = useState<number | null>(null)

  // Per-kid PIN gate (DECISIONS §17). Soft lock — gates the UI, not the
  // API. Verified-until window is server-set (1 hour) and expires
  // automatically; isUnlocked re-checks the timestamp on every render so
  // the gate re-appears once the unlock lapses.
  const isUnlocked = useKidPinStore((s) => s.isUnlocked)
  const setUnlocked = useKidPinStore((s) => s.setUnlocked)
  const verifyPin = useVerifyMemberPin(slug)
  const [pinError, setPinError] = useState<string | null>(null)

  const clearUndo = useCallback(() => setUndoTarget(null), [])

  if (member.error || today.error) {
    return <p className="text-rose-700 font-semibold">Couldn't load this member.</p>
  }
  if (member.isLoading || today.isLoading) {
    return <p className="text-brand-700">Loading…</p>
  }
  if (!member.data) return null

  const m = member.data

  // Render the PIN pad in place of the chore list when this member has a
  // PIN set and the local unlock has expired or never happened. Same
  // pattern as ParentGate uses for the parent PIN; reuses the existing
  // PinPad component (4-digit lock).
  if (m.pin_set && !isUnlocked(m.id)) {
    return (
      <div
        className="mx-auto max-w-lg pt-10"
        style={{ ['--accent' as string]: m.color }}
      >
        <div className="flex items-center gap-3 mb-6">
          <Link
            to="/"
            className="min-h-touch min-w-touch px-5 rounded-2xl font-bold bg-brand-50 text-brand-700 grid place-items-center"
          >
            ← Back
          </Link>
          <div className="text-fluid-xl font-black flex items-center gap-2">
            <span aria-hidden>{m.avatar ?? '🧒'}</span>
            <span>{m.name}'s PIN</span>
          </div>
        </div>
        <p className="text-fluid-sm text-brand-700/80 mb-4">
          Tap the digits to unlock {m.name}'s chores.
        </p>
        <PinPad
          length={4}
          error={pinError}
          disabled={verifyPin.isPending}
          onComplete={(pin) => {
            setPinError(null)
            verifyPin.mutate(pin, {
              onSuccess: (data) => {
                setUnlocked(m.id, data.verified_until)
              },
              onError: () => {
                setPinError('Wrong PIN — try again.')
              },
            })
          }}
        />
      </div>
    )
  }
  const todayForMember = today.data?.members.find((x) => x.id === m.id)
  const instances = todayForMember?.instances ?? []
  const doneCount = instances.filter((i) =>
    ['done', 'done_unapproved', 'skipped'].includes(i.state),
  ).length
  const allDone = instances.length > 0 && doneCount === instances.length

  const pointsToday = instances
    .filter((i) => i.state === 'done')
    .reduce((sum, i) => sum + i.points, 0)

  const handleTap = (id: number) => {
    complete.mutate(id, {
      onSuccess: (inst) => {
        setUndoTarget(id)
        playChime()
        // Only full DONE earns a confetti pop; DONE_UNAPPROVED waits on
        // the parent's approve event (UI won't see it here anyway).
        if (inst.state === 'done') {
          fireConfetti({ accent: m.color })
        }
      },
    })
  }

  return (
    <div
      className="mx-auto max-w-5xl"
      style={{ ['--accent' as string]: m.color }}
    >
      <div className="flex items-center gap-4 mb-8 flex-wrap">
        <Link
          to="/"
          className="min-h-touch min-w-touch px-5 rounded-2xl font-bold bg-brand-50 text-brand-700 grid place-items-center"
        >
          ← Back
        </Link>
        <div className="themed-soft rounded-xl4 px-6 py-4 flex-1 flex items-center gap-4 shadow-card">
          <span className="text-fluid-2xl" aria-hidden>
            {m.avatar ?? '🧒'}
          </span>
          <div className="min-w-0">
            <div className="text-fluid-xl font-black truncate">{m.name}</div>
            <div className="text-fluid-sm font-semibold opacity-80">
              🔥 {m.stats.streak} day streak · ⭐ {m.stats.points_this_week} this
              week · {m.stats.points_total} total
            </div>
          </div>
        </div>
        <Link
          to={`/member/${slug}/rewards`}
          className="min-h-touch px-5 rounded-2xl font-bold text-fluid-sm bg-brand-50 text-brand-700 grid place-items-center"
        >
          🎁 Rewards
        </Link>
      </div>

      {instances.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-fluid-3xl" aria-hidden>✨</div>
          <div className="mt-4 text-fluid-xl font-black text-brand-900">
            No chores today!
          </div>
        </div>
      ) : allDone ? (
        <CelebrationAllDone
          accent={m.color}
          pointsToday={pointsToday}
          streak={m.stats.streak}
        />
      ) : (
        <div className="grid gap-4 sm:gap-6">
          {instances.map((inst) => (
            <ChoreCard
              key={inst.id}
              instance={inst}
              onTap={() => handleTap(inst.id)}
              disabled={complete.isPending}
            />
          ))}
        </div>
      )}

      {undoTarget !== null && (
        <UndoToast
          seconds={4}
          onUndo={() => {
            undo.mutate(undoTarget)
            clearUndo()
          }}
          onExpire={clearUndo}
        />
      )}
    </div>
  )
}
