import clsx from 'clsx'
import type { TodayInstance } from '../api/types'

interface ChoreCardProps {
  instance: TodayInstance
  onTap?: () => void
  disabled?: boolean
}

const STATE_LABEL: Record<TodayInstance['state'], string> = {
  pending: 'Tap when done',
  done_unapproved: '⏳ Waiting for parent',
  done: '✓ Done',
  skipped: '↷ Skipped',
  missed: '— Missed',
}

export function ChoreCard({ instance, onTap, disabled }: ChoreCardProps) {
  const finished = ['done', 'done_unapproved', 'skipped', 'missed'].includes(
    instance.state,
  )
  return (
    <button
      type="button"
      onClick={onTap}
      disabled={disabled || finished}
      className={clsx(
        'chore-card w-full min-h-touch rounded-xl4 p-6 sm:p-8 text-left flex items-center gap-5 sm:gap-8 shadow-card transition',
        finished
          ? 'bg-white/80 text-brand-700/70 opacity-80'
          : 'bg-white text-brand-900 active:scale-[0.99]',
        instance.state === 'missed' && 'line-through',
      )}
      style={{ borderLeft: '8px solid var(--accent)' }}
    >
      <span
        aria-hidden
        className="text-[clamp(2.25rem,5vw,4rem)] leading-none shrink-0"
      >
        {instance.chore_icon ?? '✨'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-fluid-lg font-black truncate">
          {instance.chore_name}
        </div>
        <div className="mt-1 text-fluid-sm font-semibold text-brand-700/80">
          {instance.points} pt{instance.points === 1 ? '' : 's'} ·{' '}
          {STATE_LABEL[instance.state]}
        </div>
      </div>
      {!finished && (
        <span
          aria-hidden
          className="text-fluid-lg font-black text-brand-600 shrink-0"
        >
          →
        </span>
      )}
    </button>
  )
}
