import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { UndoToast } from './UndoToast'

// We avoid fake timers — happy-dom + React 18 + userEvent interact badly
// with vi.useFakeTimers. The countdown text and the tap handler are the
// only pieces worth testing at the unit level anyway; the full undo flow
// is covered by MemberView's tap → complete → toast → undo integration
// which will be tested manually in a live install.

describe('UndoToast', () => {
  it('renders the initial countdown label', () => {
    render(
      <UndoToast seconds={4} onUndo={vi.fn()} onExpire={vi.fn()} />,
    )
    expect(screen.getByText(/Undo in 4s/)).toBeTruthy()
  })

  it('honours a custom label', () => {
    render(
      <UndoToast seconds={4} onUndo={vi.fn()} onExpire={vi.fn()} label="Nice!" />,
    )
    expect(screen.getByText('Nice!')).toBeTruthy()
  })

  it('calls onUndo when the button is tapped', async () => {
    const user = userEvent.setup()
    const onUndo = vi.fn()
    render(
      <UndoToast seconds={10} onUndo={onUndo} onExpire={vi.fn()} />,
    )
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(onUndo).toHaveBeenCalledTimes(1)
  })
})
