import { Link } from 'react-router-dom'
import { useToday } from '../api/hooks'
import { MemberTile } from '../components/MemberTile'

// Greeting words that rotate by hour-of-day. Simple — we don't i18n in
// v1, and "Hey family!" works for the kid audience regardless.
//
// F-U001 (UX sweep): the late-night and pre-dawn slots used to read
// "Up late?" and "Almost bedtime!" — both subtly judgmental. The
// addon doesn't enforce bedtime, so the strings carried social weight
// without operational backing. Bookend hours now greet the same
// neutral warmth as the in-day slots; bedtime enforcement is the
// parent's job, not the UI's.
function greeting(now = new Date()): string {
  const h = now.getHours()
  if (h < 5) return 'Hi there 🌙'
  if (h < 11) return 'Good morning!'
  if (h < 14) return 'Happy midday!'
  if (h < 18) return 'Hey family!'
  if (h < 22) return 'Good evening!'
  return 'Hi there 🌙'
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
      <div className="grid place-items-center min-h-[60vh] font-display">
        <div className="relative max-w-2xl w-full rounded-xl5 bg-white p-10 sm:p-14 shadow-tile text-center overflow-hidden">
          {/* scatter of decorative emojis so the blank state looks alive */}
          <span
            aria-hidden
            className="absolute -top-4 -left-2 text-fluid-2xl rotate-[-15deg] animate-sparkle"
          >
            ✨
          </span>
          <span
            aria-hidden
            className="absolute top-6 right-4 text-fluid-xl rotate-[12deg] animate-sparkle"
            style={{ animationDelay: '400ms' }}
          >
            ⭐
          </span>
          <span
            aria-hidden
            className="absolute bottom-8 -left-2 text-fluid-xl rotate-[-20deg] animate-sparkle"
            style={{ animationDelay: '700ms' }}
          >
            🎉
          </span>
          <span
            aria-hidden
            className="absolute -bottom-4 right-6 text-fluid-2xl rotate-[18deg] animate-sparkle"
            style={{ animationDelay: '250ms' }}
          >
            🏆
          </span>

          <div
            className="text-[clamp(6rem,16vw,11rem)] leading-none animate-pop-in"
            aria-hidden
          >
            👪
          </div>
          <h1 className="mt-4 text-fluid-2xl font-black bg-gradient-to-r from-brand-600 via-bubblegum-500 to-candy-500 bg-clip-text text-transparent">
            Welcome to Family Chores!
          </h1>
          <p className="mt-4 text-fluid-base text-brand-700 font-sans">
            Add your first family member to get started. Pick a color,
            choose an emoji, and assign them some chores — they'll tap
            their tile each day to see what's up.
          </p>
          <Link
            to="/parent"
            className="mt-8 inline-flex items-center gap-3 min-h-touch px-8 rounded-2xl bg-brand-600 text-white font-black text-fluid-base shadow-tile press"
          >
            <span aria-hidden>🔒</span>
            Open Parent Mode
          </Link>
          <p className="mt-6 text-fluid-xs font-semibold text-brand-700/70 uppercase tracking-wider">
            Set a PIN, then add members + chores
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
