import {
  useApproveInstance,
  useMembers,
  useChores,
  usePendingApprovals,
  useRejectInstance,
} from '../../api/hooks'

export function ApprovalQueue() {
  const pending = usePendingApprovals()
  const members = useMembers()
  const chores = useChores()
  const approve = useApproveInstance()
  const reject = useRejectInstance()

  if (pending.isLoading || members.isLoading || chores.isLoading) {
    return <p className="text-brand-700">Loading…</p>
  }
  const items = pending.data ?? []

  if (items.length === 0) {
    return (
      <div className="rounded-xl4 bg-white p-8 text-center shadow-card">
        <div className="text-fluid-2xl" aria-hidden>✅</div>
        <div className="mt-3 text-fluid-lg font-black text-brand-900">
          Nothing waiting
        </div>
        <p className="mt-2 text-fluid-sm text-brand-700">
          Approvals show up here when kids with "requires approval" tap done.
        </p>
      </div>
    )
  }

  const byMember = new Map(members.data?.map((m) => [m.id, m]))
  const byChore = new Map(chores.data?.map((c) => [c.id, c]))

  return (
    <ul className="space-y-3">
      {items.map((inst) => {
        const m = byMember.get(inst.member_id)
        const c = byChore.get(inst.chore_id)
        return (
          <li
            key={inst.id}
            className="rounded-xl4 bg-white p-5 shadow-card flex items-center gap-4"
          >
            <div className="min-w-0 flex-1">
              <div className="text-fluid-base font-black truncate">
                {c?.name ?? 'Unknown chore'}
              </div>
              <div className="text-fluid-sm font-semibold text-brand-700/80">
                {m?.name ?? `member ${inst.member_id}`} · {inst.date} ·{' '}
                {c?.points ?? 0} pt
              </div>
            </div>
            <button
              type="button"
              onClick={() =>
                reject.mutate({ id: inst.id, reason: undefined })
              }
              className="min-h-touch px-5 rounded-2xl bg-rose-100 text-rose-900 font-bold"
              disabled={reject.isPending}
            >
              Reject
            </button>
            <button
              type="button"
              onClick={() => approve.mutate(inst.id)}
              className="min-h-touch px-5 rounded-2xl bg-emerald-500 text-white font-black"
              disabled={approve.isPending}
            >
              Approve
            </button>
          </li>
        )
      })}
    </ul>
  )
}
