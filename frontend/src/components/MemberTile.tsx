import { Link } from 'react-router-dom'
import type { TodayMember } from '../api/types'
import { ProgressRing } from './ProgressRing'

interface MemberTileProps {
  member: TodayMember
}

export function MemberTile({ member }: MemberTileProps) {
  const done = member.instances.filter((i) =>
    ['done', 'done_unapproved', 'skipped'].includes(i.state),
  ).length
  const total = member.instances.length
  const pending = total - done

  return (
    <Link
      to={`/member/${member.slug}`}
      className="themed tile relative block rounded-xl4 p-6 sm:p-10 min-h-[22rem] shadow-tile transition-transform active:scale-[0.98] focus-visible:outline-offset-4 focus-visible:outline-white"
      style={{ ['--accent' as string]: member.color }}
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="text-fluid-xl font-black truncate">{member.name}</div>
          <div className="mt-2 text-fluid-sm opacity-90 font-semibold">
            {total === 0
              ? 'No chores today 🎉'
              : `${done} of ${total} done · ${pending} to go`}
          </div>
        </div>
        {member.avatar ? (
          member.avatar.startsWith('/') ? (
            <img
              src={member.avatar}
              alt=""
              className="size-24 sm:size-32 rounded-full object-cover ring-4 ring-white/40"
            />
          ) : (
            <span className="text-[clamp(3rem,8vw,6rem)]" aria-hidden>
              {member.avatar}
            </span>
          )
        ) : (
          <span className="text-[clamp(3rem,8vw,6rem)]" aria-hidden>
            🧒
          </span>
        )}
      </div>

      <div className="mt-8 flex items-end justify-between gap-6">
        <div className="text-white">
          <div className="flex items-baseline gap-2 text-fluid-sm font-semibold opacity-90">
            <span aria-hidden>🔥</span>
            <span>
              {member.stats.streak} day
              {member.stats.streak === 1 ? '' : 's'} streak
            </span>
          </div>
          <div className="mt-1 text-fluid-sm font-semibold opacity-90">
            ⭐ {member.stats.points_this_week} this week · {member.stats.points_total} total
          </div>
        </div>

        <ProgressRing
          percent={member.today_progress_pct}
          size={112}
          color="white"
          trackColor="rgba(255,255,255,0.25)"
        />
      </div>
    </Link>
  )
}
