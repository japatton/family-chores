import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * Per-kid PIN unlock state, persisted in localStorage (DECISIONS §17).
 *
 * The server doesn't issue a kid-PIN JWT — verification is per-request,
 * the response carries `verified_until` (unix seconds), and the SPA
 * tracks unlock state client-side. This matches the soft-lock framing
 * (a determined kid could clear their own browser storage to bypass;
 * that's fine, it's a casual-tampering deterrent for the
 * wall-mounted-tablet case).
 *
 * Schema choice: keyed by member_id (number) rather than slug, so a
 * rename doesn't carry old unlock state to a new entity.
 */

interface KidPinState {
  /** member_id → unix seconds at which the unlock expires. */
  unlockedUntil: Record<number, number>
  setUnlocked: (memberId: number, untilUnixSeconds: number) => void
  clear: (memberId: number) => void
  isUnlocked: (memberId: number) => boolean
}

export const useKidPinStore = create<KidPinState>()(
  persist(
    (set, get) => ({
      unlockedUntil: {},
      setUnlocked: (memberId, untilUnixSeconds) =>
        set((state) => ({
          unlockedUntil: {
            ...state.unlockedUntil,
            [memberId]: untilUnixSeconds,
          },
        })),
      clear: (memberId) =>
        set((state) => {
          const next = { ...state.unlockedUntil }
          delete next[memberId]
          return { unlockedUntil: next }
        }),
      isUnlocked: (memberId) => {
        const exp = get().unlockedUntil[memberId]
        if (!exp) return false
        return exp * 1000 > Date.now()
      },
    }),
    { name: 'family-chores-kid-pin' },
  ),
)
