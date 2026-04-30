import { useEffect } from 'react'
import { fireConfetti } from './Confetti'

interface CelebrationAllDoneProps {
  accent: string
  pointsToday: number
  streak: number
  // F-U005 (UX sweep): personalisation. Kids 4–10 light up at hearing/seeing
  // their own name — generic "You did it!" leaves the highest-leverage
  // micro-improvement on the floor.
  name?: string
}

// F-U005: deterministic per-day rotation across a small set of warm
// subhead phrasings — enough variety that the celebration feels fresh
// across a streak, low enough that the kid can anticipate the wording.
// Seeded by the local YYYY-MM-DD so the same kid's celebration on the
// same day always reads the same.
const SUBHEADS = [
  'Every chore done for today. Nice work.',
  'That was awesome — every single one.',
  'Look at you go. Day cleared.',
  'Way to crush it. All done.',
  'Total pro move. Day finished.',
] as const

function pickSubhead(): string {
  const today = new Date()
  // Day-of-year 0..365 → stable index across the day.
  const start = new Date(today.getFullYear(), 0, 0)
  const dayOfYear = Math.floor(
    (today.getTime() - start.getTime()) / (1000 * 60 * 60 * 24),
  )
  return SUBHEADS[dayOfYear % SUBHEADS.length]
}

export function CelebrationAllDone({
  accent,
  pointsToday,
  streak,
  name,
}: CelebrationAllDoneProps) {
  useEffect(() => {
    // One burst on mount. A subsequent burst fires two seconds later for
    // a longer-feeling "that was cool" moment without overwhelming.
    fireConfetti({ accent })
    const id = window.setTimeout(() => fireConfetti({ accent, particles: 60 }), 1400)
    return () => window.clearTimeout(id)
  }, [accent])

  return (
    <div
      className="themed rounded-xl4 p-10 sm:p-16 text-center shadow-tile relative overflow-hidden"
      style={{ ['--accent' as string]: accent }}
    >
      <div
        aria-hidden
        className="absolute inset-0 pointer-events-none opacity-20"
        style={{
          background:
            'radial-gradient(circle at 20% 20%, white 0%, transparent 40%), radial-gradient(circle at 80% 80%, white 0%, transparent 40%)',
        }}
      />
      {/*
       * F-U003 (UX sweep): the celebration emoji used to bounce via inline
       * `style={{ animation: 'bounce ...' }}`, which bypassed the global
       * `prefers-reduced-motion` block in globals.css. Switched to the
       * `animate-celebrate-bounce` Tailwind utility (custom keyframe in
       * tailwind.config.ts) which IS gated by the reduced-motion media
       * query. Visual is identical for users with motion enabled.
       */}
      <div
        aria-hidden
        className="text-[clamp(4rem,10vw,8rem)] leading-none inline-block animate-celebrate-bounce"
      >
        🎉
      </div>
      <h2 className="mt-6 text-fluid-2xl font-black">
        {name ? `You did it, ${name}!` : 'You did it!'}
      </h2>
      <p className="mt-3 text-fluid-base opacity-90">{pickSubhead()}</p>
      <dl className="mt-8 grid grid-cols-2 gap-4 max-w-md mx-auto">
        <div className="rounded-2xl bg-white/20 p-4">
          <dt className="text-fluid-xs font-semibold opacity-80">Earned today</dt>
          <dd className="text-fluid-xl font-black">⭐ {pointsToday}</dd>
        </div>
        <div className="rounded-2xl bg-white/20 p-4">
          <dt className="text-fluid-xs font-semibold opacity-80">Streak</dt>
          <dd className="text-fluid-xl font-black">
            🔥 {streak} day{streak === 1 ? '' : 's'}
          </dd>
        </div>
      </dl>
      <p className="mt-6 text-fluid-sm opacity-80 italic">Same time tomorrow?</p>
    </div>
  )
}
