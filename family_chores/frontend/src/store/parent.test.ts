import { act } from '@testing-library/react'
import { describe, expect, it, beforeEach } from 'vitest'
import { useParentStore } from './parent'

beforeEach(() => {
  useParentStore.getState().clear()
})

describe('useParentStore', () => {
  it('isActive returns false when no token set', () => {
    expect(useParentStore.getState().isActive()).toBe(false)
    expect(useParentStore.getState().secondsUntilExpiry()).toBe(0)
  })

  it('isActive returns true within expiry window', () => {
    const future = Math.floor(Date.now() / 1000) + 300
    act(() => useParentStore.getState().setToken('tok-1', future))
    expect(useParentStore.getState().isActive()).toBe(true)
    expect(useParentStore.getState().secondsUntilExpiry()).toBeGreaterThan(0)
  })

  it('isActive returns false after expiry', () => {
    act(() => useParentStore.getState().setToken('tok', 1))
    expect(useParentStore.getState().isActive()).toBe(false)
  })

  it('clear() drops the token', () => {
    const future = Math.floor(Date.now() / 1000) + 300
    act(() => useParentStore.getState().setToken('tok', future))
    act(() => useParentStore.getState().clear())
    expect(useParentStore.getState().token).toBeNull()
    expect(useParentStore.getState().isActive()).toBe(false)
  })

  it('persists to localStorage', () => {
    const future = Math.floor(Date.now() / 1000) + 300
    act(() => useParentStore.getState().setToken('tok-persist', future))
    const raw = window.localStorage.getItem('family-chores-parent')
    expect(raw).not.toBeNull()
    expect(raw).toContain('tok-persist')
  })

  it('markActive updates lastActivity but not the token', () => {
    const future = Math.floor(Date.now() / 1000) + 300
    act(() => useParentStore.getState().setToken('tok', future))
    const before = useParentStore.getState().lastActivity
    act(() => useParentStore.getState().markActive())
    const after = useParentStore.getState().lastActivity
    expect(after).toBeGreaterThanOrEqual(before)
    expect(useParentStore.getState().token).toBe('tok')
  })
})
