import { useCallback, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  useCompleteInstance,
  useMember,
  useToday,
  useUndoInstance,
} from '../api/hooks'
import { ChoreCard } from '../components/ChoreCard'
import { UndoToast } from '../components/UndoToast'

export function MemberView() {
  const { slug = '' } = useParams()
  const member = useMember(slug)
  const today = useToday()

  const complete = useCompleteInstance()
  const undo = useUndoInstance()
  const [undoTarget, setUndoTarget] = useState<number | null>(null)

  const clearUndo = useCallback(() => setUndoTarget(null), [])

  if (member.error || today.error) {
    return <p className="text-rose-700 font-semibold">Couldn't load this member.</p>
  }
  if (member.isLoading || today.isLoading) {
    return <p className="text-brand-700">Loading…</p>
  }
  if (!member.data) return null

  const m = member.data
  const todayForMember = today.data?.members.find((x) => x.id === m.id)
  const instances = todayForMember?.instances ?? []
  const doneCount = instances.filter((i) =>
    ['done', 'done_unapproved', 'skipped'].includes(i.state),
  ).length
  const allDone = instances.length > 0 && doneCount === instances.length

  const handleTap = (id: number) => {
    complete.mutate(id, {
      onSuccess: () => setUndoTarget(id),
    })
  }

  return (
    <div
      className="mx-auto max-w-5xl"
      style={{ ['--accent' as string]: m.color }}
    >
      <div className="flex items-center gap-4 mb-8">
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
      </div>

      {instances.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-fluid-3xl" aria-hidden>✨</div>
          <div className="mt-4 text-fluid-xl font-black text-brand-900">
            No chores today!
          </div>
        </div>
      ) : allDone ? (
        <div className="text-center py-16">
          <div className="text-fluid-3xl" aria-hidden>🎉</div>
          <div className="mt-4 text-fluid-xl font-black text-brand-900">
            All done for today
          </div>
          <p className="mt-3 text-fluid-base text-brand-700">
            Nice work — see you tomorrow.
          </p>
        </div>
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
