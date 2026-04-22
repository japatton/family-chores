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
})
