import { useActivityLog } from '../../api/hooks'

export function ActivityTab() {
  const log = useActivityLog(50, 0)

  if (log.isLoading) return <p className="text-brand-700">Loading…</p>
  if (log.error)
    return <p className="text-rose-700 font-semibold">Couldn't load activity.</p>

  const entries = log.data?.entries ?? []
  if (entries.length === 0) {
    return (
      <p className="text-brand-700/80 text-fluid-sm">
        No activity yet. Actions here will include member/chore changes,
        completions, approvals, and manual point adjustments.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {entries.map((e) => (
        <li
          key={e.id}
          className="rounded-2xl bg-white px-4 py-3 shadow-card text-fluid-sm"
        >
          <div className="flex items-baseline justify-between gap-4">
            <span className="font-black text-brand-900">{e.action}</span>
            <span className="text-brand-700/70 font-mono text-fluid-xs">
              {new Date(e.ts).toLocaleString()}
            </span>
          </div>
          <div className="text-brand-700/80 font-semibold">{e.actor}</div>
          {Object.keys(e.payload).length > 0 && (
            <pre className="mt-1 text-xs font-mono whitespace-pre-wrap text-brand-700/80">
              {JSON.stringify(e.payload, null, 0)}
            </pre>
          )}
        </li>
      ))}
    </ul>
  )
}
