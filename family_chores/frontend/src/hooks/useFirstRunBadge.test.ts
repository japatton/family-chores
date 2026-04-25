import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useFirstRunBadge } from './useFirstRunBadge'

const KEY = 'fc.test.firstRun'

beforeEach(() => {
  // setup.ts clears localStorage between tests, but be explicit here
  // since tests in this file all share the key.
  window.localStorage.clear()
})

describe('useFirstRunBadge', () => {
  it('returns active=true on first ever load', () => {
    const { result } = renderHook(() => useFirstRunBadge(KEY))
    expect(result.current[0]).toBe(true)
  })

  it('returns active=false when the key already exists', () => {
    window.localStorage.setItem(KEY, '1')
    const { result } = renderHook(() => useFirstRunBadge(KEY))
    expect(result.current[0]).toBe(false)
  })

  it('dismiss flips active to false and writes to localStorage', () => {
    const { result } = renderHook(() => useFirstRunBadge(KEY))
    expect(result.current[0]).toBe(true)

    act(() => {
      result.current[1]()
    })

    expect(result.current[0]).toBe(false)
    expect(window.localStorage.getItem(KEY)).not.toBeNull()
  })

  it('a second render after dismiss returns active=false', () => {
    const { result, rerender } = renderHook(() => useFirstRunBadge(KEY))
    act(() => {
      result.current[1]()
    })
    rerender()
    expect(result.current[0]).toBe(false)

    // A fresh hook on the same key (simulates a page reload) sees the
    // persisted dismissal too.
    const { result: result2 } = renderHook(() => useFirstRunBadge(KEY))
    expect(result2.current[0]).toBe(false)
  })

  it('different keys are independent', () => {
    const { result: a } = renderHook(() => useFirstRunBadge('fc.testA'))
    const { result: b } = renderHook(() => useFirstRunBadge('fc.testB'))
    act(() => {
      a.current[1]()
    })
    expect(a.current[0]).toBe(false)
    expect(b.current[0]).toBe(true)
  })
})
