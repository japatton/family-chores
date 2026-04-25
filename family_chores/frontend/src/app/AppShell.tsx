import { Link, Outlet, useLocation } from 'react-router-dom'
import { useInfo } from '../api/hooks'
import { useWSConnected } from '../ws/provider'
import { AnimatedTitle } from '../components/AnimatedTitle'
import { Banner } from '../components/Banner'
import { DecorativeBackground } from '../components/DecorativeBackground'
import { SoundToggle } from '../components/SoundToggle'

export function AppShell() {
  const info = useInfo()
  const connected = useWSConnected()
  const loc = useLocation()

  const bootstrapBanner = info.data?.bootstrap?.banner ?? null
  const haBanner =
    info.data && info.data.ha_connected === false
      ? 'Home Assistant bridge not connected — chores still work, but mirroring to HA is paused.'
      : null
  // F-S004: surfaces when startup catch-up rollover failed. Today's
  // chore instances may be empty until something else triggers
  // generate_instances (creating/editing a chore, or admin rebuild).
  const rolloverWarning = info.data?.rollover_warning ?? null

  return (
    <div className="min-h-screen flex flex-col relative">
      <DecorativeBackground />
      <header className="flex items-center justify-between px-6 py-4 sm:px-10 sm:py-6 border-b-2 border-brand-100 sticky top-0 z-10 font-display shadow-pop"
        style={{
          backgroundImage:
            'linear-gradient(90deg, rgba(236,72,153,0.12), rgba(99,102,241,0.18), rgba(14,165,233,0.12))',
          backgroundColor: 'rgba(255,255,255,0.85)',
          backdropFilter: 'blur(12px)',
        }}
      >
        <Link to="/" className="block py-2">
          <AnimatedTitle text="Family Chores" />
        </Link>
        <nav className="flex items-center gap-3">
          {!connected && (
            <span
              className="px-3 py-1 rounded-full text-fluid-xs font-semibold text-amber-800 bg-amber-100"
              aria-live="polite"
            >
              reconnecting…
            </span>
          )}
          <SoundToggle />
          <Link
            to="/parent"
            className={
              'min-h-touch px-5 rounded-2xl font-bold grid place-items-center ' +
              (loc.pathname.startsWith('/parent')
                ? 'bg-brand-600 text-white'
                : 'bg-brand-50 text-brand-700 hover:bg-brand-100')
            }
          >
            Parent
          </Link>
        </nav>
      </header>

      {(bootstrapBanner || haBanner || rolloverWarning) && (
        <div className="px-6 sm:px-10 pt-4 space-y-2">
          {bootstrapBanner && <Banner variant="warn">{bootstrapBanner}</Banner>}
          {rolloverWarning && (
            <Banner variant="warn">
              Startup catch-up rollover failed — today’s chores may be empty
              until you add or edit a chore. Check the add-on log for the
              full error: <code>{rolloverWarning}</code>
            </Banner>
          )}
          {haBanner && <Banner variant="info">{haBanner}</Banner>}
        </div>
      )}

      <main className="flex-1 px-6 sm:px-10 py-6 sm:py-10 relative z-[1]">
        <Outlet />
      </main>
    </div>
  )
}
