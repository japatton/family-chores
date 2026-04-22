import { useToday } from '../api/hooks'
import { MemberTile } from '../components/MemberTile'

// Greeting words that rotate by hour-of-day. Simple — we don't i18n in
// v1, and "Hey family!" works for the kid audience regardless.
function greeting(now = new Date()): string {
  const h = now.getHours()
  if (h < 5) return 'Up late?'
  if (h < 11) return 'Good morning!'
  if (h < 14) return 'Happy midday!'
  if (h < 18) return 'Hey family!'
  if (h < 22) return 'Good evening!'
  return 'Almost bedtime!'
}

function formattedDate(iso: string | undefined): string {
  if (!iso) return ''
  const d = new Date(`${iso}T12:00:00`) // midday avoids TZ surprises
  return d.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

export function TodayView() {
  const today = useToday()

  if (today.isLoading) {
    return (
      <div className="grid place-items-center min-h-[40vh] text-fluid-base text-brand-700 font-display">
        <span className="animate-pop-in" aria-hidden>✨</span>
      </div>
    )
  }
  if (today.error) {
    return (
      <div className="grid place-items-center min-h-[40vh] text-fluid-base text-rose-700 font-display">
        Couldn't reach the backend.
      </div>
    )
  }

  const members = today.data?.members ?? []

  if (members.length === 0) {
    return (
      <div className="grid place-items-center min-h-[50vh] text-center max-w-xl mx-auto font-display">
        <div>
          <div className="text-[clamp(5rem,12vw,9rem)] mb-4 animate-sparkle" aria-hidden>
            👪
          </div>
          <div className="text-fluid-xl font-black text-brand-900">
            Add your first family member
          </div>
          <p className="mt-4 text-fluid-base text-brand-700 font-sans">
            Tap <span className="font-black">Parent</span> at the top to set a
            PIN, then add members and chores. Kids tap their tile to see
            what's up today.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-[100rem] font-display">
      <header className="mb-6 sm:mb-10 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <div className="text-fluid-sm font-bold text-brand-700/80 uppercase tracking-wider">
            {formattedDate(today.data?.date)}
          </div>
          <h1 className="text-fluid-2xl font-black text-brand-900 mt-1">
            {greeting()}
          </h1>
        </div>
        <div className="text-fluid-base font-bold text-brand-700 rounded-full bg-white/70 backdrop-blur px-5 py-2 shadow-pop">
          {members.length} player{members.length === 1 ? '' : 's'} · tap a tile to start
        </div>
      </header>

      <div className="grid gap-6 sm:gap-10 grid-cols-1 md:grid-cols-2">
        {members.map((m) => (
          <MemberTile key={m.id} member={m} />
        ))}
      </div>
    </div>
  )
}
