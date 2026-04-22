import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UIState {
  soundEnabled: boolean
  setSoundEnabled: (v: boolean) => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      soundEnabled: false,
      setSoundEnabled: (v) => set({ soundEnabled: v }),
    }),
    { name: 'family-chores-ui' },
  ),
)
