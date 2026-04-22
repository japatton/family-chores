import { act } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useUIStore } from './ui'

describe('useUIStore', () => {
  it('defaults soundEnabled to false', () => {
    expect(useUIStore.getState().soundEnabled).toBe(false)
  })

  it('setSoundEnabled toggles and persists', () => {
    act(() => useUIStore.getState().setSoundEnabled(true))
    expect(useUIStore.getState().soundEnabled).toBe(true)
    const raw = window.localStorage.getItem('family-chores-ui')
    expect(raw).toContain('"soundEnabled":true')
  })
})
