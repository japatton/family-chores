import { useState } from 'react'

/**
 * One-shot first-run discoverability flag, persisted in localStorage.
 *
 * Returns `[active, dismiss]` — `active` is true until `dismiss()` is
 * called for the first time on this device, after which it stays false
 * across page reloads.
 *
 * DECISIONS §13 §6.2 calls for app_config-backed persistence (per-
 * household, follows the user across browsers) but settled on
 * localStorage as the v1 store: simpler, no schema change required,
 * and the cost of a returning parent seeing the badge once on a fresh
 * browser is low.
 *
 * Defensive about localStorage failures (private-mode Safari, disabled
 * storage, etc.) — falls through to in-memory state with the badge
 * defaulting to "active" so the affordance is at least discoverable.
 */
export function useFirstRunBadge(key: string): [boolean, () => void] {
  const [active, setActive] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(key) === null
    } catch {
      return true
    }
  })

  const dismiss = (): void => {
    try {
      window.localStorage.setItem(key, String(Date.now()))
    } catch {
      // ignore — fall through to in-memory dismissal
    }
    setActive(false)
  }

  return [active, dismiss]
}
