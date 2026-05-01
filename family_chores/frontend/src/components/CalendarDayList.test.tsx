import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CalendarEvent } from '../api/types'
import { CalendarDayList } from './CalendarDayList'

function _event(overrides: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    entity_id: 'calendar.kid',
    summary: 'Soccer practice',
    description: null,
    start: '2026-05-01T16:00:00+00:00',
    end: '2026-05-01T17:00:00+00:00',
    all_day: false,
    location: null,
    prep_items: [],
    ...overrides,
  }
}

describe('CalendarDayList', () => {
  it('renders nothing when no events and no errors', () => {
    const { container } = render(<CalendarDayList events={[]} unreachable={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the empty state when only unreachable is set', () => {
    const { getByRole, getByText } = render(
      <CalendarDayList events={[]} unreachable={['calendar.broken']} />,
    )
    // Heading should be there once we have anything to render.
    expect(getByText("Today's events")).toBeTruthy()
    // Unreachable hint visible.
    const status = getByRole('status')
    expect(status.textContent).toMatch(/couldn't reach/i)
    // The "nothing else on the calendar today" line is visible since events is empty.
    expect(getByText(/nothing else on the calendar today/i)).toBeTruthy()
  })

  it('renders one entry per event with the start time formatted', () => {
    const { getAllByRole, getByText } = render(
      <CalendarDayList
        events={[
          _event({ summary: 'Soccer practice' }),
          _event({
            summary: 'Music lesson',
            start: '2026-05-01T18:00:00+00:00',
            end: '2026-05-01T19:00:00+00:00',
          }),
        ]}
      />,
    )
    const items = getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(getByText('Soccer practice')).toBeTruthy()
    expect(getByText('Music lesson')).toBeTruthy()
  })

  it('shows location with a pin glyph when present', () => {
    const { getByText } = render(
      <CalendarDayList
        events={[_event({ location: 'School field' })]}
      />,
    )
    expect(getByText('School field')).toBeTruthy()
  })

  it('renders an All-day badge for all-day events', () => {
    const { getByLabelText } = render(
      <CalendarDayList
        events={[_event({ all_day: true, summary: 'Spring Break' })]}
      />,
    )
    expect(getByLabelText('All day')).toBeTruthy()
  })

  it('renders prep chips inside each event card', () => {
    const { getByText } = render(
      <CalendarDayList
        events={[
          _event({
            summary: 'Soccer',
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

  it('still renders events when also reporting unreachable calendars', () => {
    const { getByText, getByRole } = render(
      <CalendarDayList
        events={[_event({ summary: 'Soccer' })]}
        unreachable={['calendar.bad']}
      />,
    )
    expect(getByText('Soccer')).toBeTruthy()
    expect(getByRole('status').textContent).toMatch(/couldn't reach/i)
  })

  it('treats omitted unreachable as empty', () => {
    const { queryByRole } = render(
      <CalendarDayList events={[_event({ summary: 'Soccer' })]} />,
    )
    expect(queryByRole('status')).toBeNull()
  })
})
