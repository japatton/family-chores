import { create } from 'zustand';
import { persist } from 'zustand/middleware';
export const useUIStore = create()(persist((set) => ({
    soundEnabled: false,
    setSoundEnabled: (v) => set({ soundEnabled: v }),
}), { name: 'family-chores-ui' }));
