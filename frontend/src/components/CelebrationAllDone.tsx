import { useEffect } from 'react'
import { fireConfetti } from './Confetti'

interface CelebrationAllDoneProps {
  accent: string
  pointsToday: number
  streak: number
}

export function CelebrationAllDone({
  accent,
  pointsToday,
  streak,
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
      <div
        aria-hidden
        className="text-[clamp(4rem,10vw,8rem)] leading-none inline-block"
        style={{ animation: 'bounce 2.4s ease-in-out infinite' }}
      >
        🎉
      </div>
      <h2 className="mt-6 text-fluid-2xl font-black">You did it!</h2>
      <p className="mt-3 text-fluid-base opacity-90">
        Every chore done for today. Nice work.
      </p>
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
