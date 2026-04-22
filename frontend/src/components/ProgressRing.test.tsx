import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ProgressRing } from './ProgressRing'

describe('ProgressRing', () => {
  it('renders the integer percentage as centered text', () => {
    const { container } = render(<ProgressRing percent={42} />)
    const text = container.querySelector('text')
    expect(text?.textContent).toBe('42%')
  })

  it('rounds the displayed percent to an integer', () => {
    const { container } = render(<ProgressRing percent={66.66} />)
    expect(container.querySelector('text')?.textContent).toBe('67%')
  })

  it('clamps values above 100 and below 0', () => {
    const { container: high } = render(<ProgressRing percent={150} />)
    expect(high.querySelector('text')?.textContent).toBe('100%')
    const { container: low } = render(<ProgressRing percent={-25} />)
    expect(low.querySelector('text')?.textContent).toBe('0%')
  })

  it('exposes the label for aria', () => {
    const { container } = render(
      <ProgressRing percent={50} label="Alice's progress today" />,
    )
    expect(container.querySelector('svg')?.getAttribute('aria-label')).toBe(
      "Alice's progress today",
    )
  })
})
