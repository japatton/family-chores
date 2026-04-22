import { Link, Outlet, useLocation } from 'react-router-dom'
import { useInfo } from '../api/hooks'
import { useWSConnected } from '../ws/provider'
import { Banner } from '../components/Banner'
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

  return (
    <div className="min-h-screen flex flex-col">
      <header className="flex items-center justify-between px-6 py-4 sm:px-10 sm:py-6 border-b border-brand-100 bg-white/70 backdrop-blur sticky top-0 z-10">
        <Link to="/" className="flex items-center gap-3 text-fluid-lg font-black text-brand-700">
          <span aria-hidden className="text-fluid-xl">🧹</span>
          <span>Family Chores</span>
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

      {(bootstrapBanner || haBanner) && (
        <div className="px-6 sm:px-10 pt-4 space-y-2">
          {bootstrapBanner && <Banner variant="warn">{bootstrapBanner}</Banner>}
          {haBanner && <Banner variant="info">{haBanner}</Banner>}
        </div>
      )}

      <main className="flex-1 px-6 sm:px-10 py-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  )
}
