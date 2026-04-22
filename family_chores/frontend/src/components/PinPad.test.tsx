import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PinPad } from './PinPad'

describe('PinPad', () => {
  it('calls onComplete when the configured number of digits are entered', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<PinPad length={4} onComplete={onComplete} />)

    await user.click(screen.getByRole('button', { name: '1' }))
    await user.click(screen.getByRole('button', { name: '2' }))
    await user.click(screen.getByRole('button', { name: '3' }))
    await user.click(screen.getByRole('button', { name: '4' }))

    expect(onComplete).toHaveBeenCalledTimes(1)
    expect(onComplete).toHaveBeenCalledWith('1234')
  })

  it('clears current input when an error is shown', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    const { rerender } = render(<PinPad length={4} onComplete={onComplete} />)

    await user.click(screen.getByRole('button', { name: '1' }))
    await user.click(screen.getByRole('button', { name: '2' }))

    rerender(<PinPad length={4} onComplete={onComplete} error="nope" />)
    expect(screen.getByRole('alert').textContent).toBe('nope')
    // After the error clears the slots, we need 4 fresh digits to re-fire.
    onComplete.mockClear()
    await user.click(screen.getByRole('button', { name: '1' }))
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('backspace removes the last digit', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<PinPad length={4} onComplete={onComplete} />)

    await user.click(screen.getByRole('button', { name: '1' }))
    await user.click(screen.getByRole('button', { name: '2' }))
    await user.click(screen.getByRole('button', { name: 'backspace' }))
    await user.click(screen.getByRole('button', { name: '9' }))
    await user.click(screen.getByRole('button', { name: '9' }))
    await user.click(screen.getByRole('button', { name: '9' }))

    expect(onComplete).toHaveBeenCalledWith('1999')
  })

  it('disabled mode blocks input', async () => {
    const user = userEvent.setup()
    const onComplete = vi.fn()
    render(<PinPad length={4} onComplete={onComplete} disabled />)

    await user.click(screen.getByRole('button', { name: '1' }))
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('does not refire onComplete when the parent re-renders with a new callback', async () => {
    // Regression: inline `onComplete={(pin) => verify.mutate(pin)}` in
    // the parent PIN flow was firing multiple times because each parent
    // re-render created a new function reference, re-running the effect
    // while `value` was still full — producing duplicate POSTs and a
    // white-screen race after the PIN was accepted.
    const user = userEvent.setup()
    const calls: string[] = []

    function Harness() {
      const [, setBump] = useState(0)
      return (
        <>
          <button
            type="button"
            data-testid="bump"
            onClick={() => setBump((n) => n + 1)}
          >
            bump
          </button>
          <PinPad
            length={4}
            onComplete={(pin) => {
              // Inline on purpose — new reference every render.
              calls.push(pin)
            }}
          />
        </>
      )
    }

    render(<Harness />)
    for (const d of ['1', '2', '3', '4']) {
      await user.click(screen.getByRole('button', { name: d }))
    }
    expect(calls).toEqual(['1234'])

    await user.click(screen.getByTestId('bump'))
    await user.click(screen.getByTestId('bump'))
    expect(calls).toEqual(['1234'])
  })
})
