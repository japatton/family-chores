import { beforeEach, describe, expect, it } from 'vitest'

import { useKidPinStore } from './kidPin'

beforeEach(() => {
  // Persist middleware writes to localStorage; clear so tests don't
  // see leftover unlock state from the previous test.
  window.localStorage.clear()
  useKidPinStore.setState({ unlockedUntil: {} })
})

describe('kidPinStore', () => {
  it('isUnlocked returns false for an unknown member', () => {
    expect(useKidPinStore.getState().isUnlocked(42)).toBe(false)
  })

  it('setUnlocked + isUnlocked round-trip', () => {
    const futureUnix = Math.floor(Date.now() / 1000) + 3600
    useKidPinStore.getState().setUnlocked(42, futureUnix)
    expect(useKidPinStore.getState().isUnlocked(42)).toBe(true)
  })

  it('isUnlocked returns false once the unlock has expired', () => {
    const pastUnix = Math.floor(Date.now() / 1000) - 1
    useKidPinStore.getState().setUnlocked(42, pastUnix)
    expect(useKidPinStore.getState().isUnlocked(42)).toBe(false)
  })

  it('clear removes the unlock for a single member', () => {
    const futureUnix = Math.floor(Date.now() / 1000) + 3600
    useKidPinStore.getState().setUnlocked(1, futureUnix)
    useKidPinStore.getState().setUnlocked(2, futureUnix)
    useKidPinStore.getState().clear(1)
    expect(useKidPinStore.getState().isUnlocked(1)).toBe(false)
    expect(useKidPinStore.getState().isUnlocked(2)).toBe(true)
  })

  it('persists to localStorage under the family-chores-kid-pin key', () => {
    const futureUnix = Math.floor(Date.now() / 1000) + 3600
    useKidPinStore.getState().setUnlocked(7, futureUnix)
    const raw = window.localStorage.getItem('family-chores-kid-pin')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw as string)
    expect(parsed.state.unlockedUntil[7]).toBe(futureUnix)
  })
})
