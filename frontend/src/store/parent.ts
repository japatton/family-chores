import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ParentState {
  token: string | null
  expiresAt: number // unix seconds
  lastActivity: number // ms since epoch
  setToken: (token: string, expiresAt: number) => void
  clear: () => void
  markActive: () => void
  isActive: () => boolean
  secondsUntilExpiry: () => number
}

export const useParentStore = create<ParentState>()(
  persist(
    (set, get) => ({
      token: null,
      expiresAt: 0,
      lastActivity: 0,
      setToken: (token, expiresAt) =>
        set({ token, expiresAt, lastActivity: Date.now() }),
      clear: () => set({ token: null, expiresAt: 0, lastActivity: 0 }),
      markActive: () => set({ lastActivity: Date.now() }),
      isActive: () => {
        const { token, expiresAt } = get()
        return !!token && expiresAt * 1000 > Date.now()
      },
      secondsUntilExpiry: () => {
        const { expiresAt } = get()
        if (!expiresAt) return 0
        return Math.max(0, expiresAt - Math.floor(Date.now() / 1000))
      },
    }),
    { name: 'family-chores-parent' },
  ),
)
