import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../api/types'
import { PrepChipStrip } from './PrepChipStrip'

function _event(
  overrides: Partial<CalendarEvent> & { prep_items: CalendarEvent['prep_items'] },
): CalendarEvent {
  return {
    entity_id: 'calendar.kid',
    summary: 'Soccer',
    description: null,
    start: '2026-05-01T16:00:00+00:00',
    end: '2026-05-01T17:00:00+00:00',
    all_day: false,
    location: null,
    ...overrides,
  }
}

describe('PrepChipStrip', () => {
  it('renders nothing when no prep items', () => {
    const { container } = render(
      <PrepChipStrip events={[_event({ prep_items: [] })]} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing for an empty event list', () => {
    const { container } = render(<PrepChipStrip events={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders one chip per unique prep item', () => {
    const { getByText } = render(
      <PrepChipStrip
        events={[
          _event({
            prep_items: [
              { label: 'cleats', icon: '🥾' },
              { label: 'water bottle', icon: '💧' },
            ],
          }),
        ]}
      />,
    )
    expect(getByText('cleats')).toBeTruthy()
    expect(getByText('water bottle')).toBeTruthy()
  })

  it('dedupes prep items across multiple events (case-insensitive)', () => {
    const { queryAllByText } = render(
      <PrepChipStrip
        events={[
          _event({
            summary: 'Soccer A',
            prep_items: [{ label: 'cleats', icon: '🥾' }],
          }),
          _event({
            summary: 'Soccer B',
            prep_items: [{ label: 'Cleats', icon: '🥾' }],
          }),
        ]}
      />,
    )
    expect(queryAllByText('cleats')).toHaveLength(1)
  })

  it('prefers an icon-bearing duplicate over a text-only one', () => {
    const { container } = render(
      <PrepChipStrip
        events={[
          _event({
            summary: 'A',
            prep_items: [{ label: 'lunch', icon: null }],
          }),
          _event({
            summary: 'B',
            prep_items: [{ label: 'lunch', icon: '🍱' }],
          }),
        ]}
      />,
    )
    expect(container.textContent).toContain('🍱')
    expect(container.textContent).toContain('lunch')
  })

  it('collapses overflow into a +N more pill', () => {
    const items = Array.from({ length: 7 }, (_, i) => ({
      label: `item${i}`,
      icon: null as string | null,
    }))
    const { getByText, queryByText } = render(
      <PrepChipStrip
        maxChips={4}
        events={[_event({ prep_items: items })]}
      />,
    )
    expect(getByText('item0')).toBeTruthy()
    expect(getByText('item3')).toBeTruthy()
    expect(queryByText('item4')).toBeNull()
    expect(getByText('+3 more')).toBeTruthy()
  })

  it('preserves first-seen order across events', () => {
    const { container } = render(
      <PrepChipStrip
        events={[
          _event({
            summary: 'First',
            prep_items: [{ label: 'C', icon: null }],
          }),
          _event({
            summary: 'Second',
            prep_items: [
              { label: 'A', icon: null },
              { label: 'B', icon: null },
            ],
          }),
        ]}
      />,
    )
    // Outer chip span carries `rounded-full` — querying for that class
    // gives us one element per chip in render order. (Plain
    // `querySelectorAll('span')` returns nested spans too.)
    const chips = Array.from(container.querySelectorAll('span.rounded-full'))
    expect(chips.map((c) => c.textContent?.trim())).toEqual(['C', 'A', 'B'])
  })
})
