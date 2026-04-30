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

  // F-U002 (UX sweep): ratio-based progress framing. The old phrasing
  // "X of Y done · Z to go" was math-correct but read as a wall of work
  // for high-N kid mornings. Switching to motivational copy at thresholds
  // that match how kids respond — "halfway", "almost there", a fresh
  // start invitation when nothing's done yet.
  const ratio = total === 0 ? 0 : done / total
  const progressPhrase =
    total === 0
      ? 'No chores today 🎉'
      : ratio === 1
        ? 'All done — way to go! 🎉'
        : ratio >= 0.8
          ? `Almost there! ${total - done} left`
          : ratio >= 0.5
            ? 'Halfway through ✨'
            : ratio > 0
              ? `${done} done — keep going!`
              : `Let's get started — ${total} chore${total === 1 ? '' : 's'} today`

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
            {progressPhrase}
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
