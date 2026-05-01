import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { CalendarEvent } from '../api/types'
import { MonthGrid } from './MonthGrid'

function _event(
  overrides: Partial<CalendarEvent> & { entity_id: string; summary: string; start: string; end: string },
): CalendarEvent {
  return {
    description: null,
    all_day: false,
    location: null,
    prep_items: [],
    ...overrides,
  }
}

describe('MonthGrid', () => {
  it('renders 42 day cells (6 rows × 7 cols)', () => {
    const { getAllByRole } = render(
      <MonthGrid monthStart={new Date(2026, 4, 1)} events={[]} />,
    )
    expect(getAllByRole('gridcell')).toHaveLength(42)
  })

  it('renders weekday headers', () => {
    const { getAllByRole } = render(
      <MonthGrid monthStart={new Date(2026, 4, 1)} events={[]} />,
    )
    expect(getAllByRole('columnheader')).toHaveLength(7)
  })

  it('places an event on its start day cell', () => {
    const { getByText } = render(
      <MonthGrid
        monthStart={new Date(2026, 4, 1)}
        events={[
          _event({
            entity_id: 'calendar.kid',
            summary: 'Soccer practice',
            // 2026-05-04 16:00 local — note: getMonth is 0-indexed,
            // we construct via local time so the month is May.
            start: new Date(2026, 4, 4, 16, 0).toISOString(),
            end: new Date(2026, 4, 4, 17, 0).toISOString(),
          }),
        ]}
      />,
    )
    expect(getByText(/Soccer practice/)).toBeTruthy()
  })

  it('collapses 4+ events on a single day into +N more', () => {
    const events: CalendarEvent[] = []
    for (let i = 0; i < 5; i++) {
      events.push(
        _event({
          entity_id: 'calendar.kid',
          summary: `event-${i}`,
          start: new Date(2026, 4, 4, 9 + i, 0).toISOString(),
          end: new Date(2026, 4, 4, 10 + i, 0).toISOString(),
        }),
      )
    }
    const { getByText } = render(
      <MonthGrid monthStart={new Date(2026, 4, 1)} events={events} />,
    )
    expect(getByText(/\+2 more/)).toBeTruthy()
  })

  it('all-day event shows summary without a time prefix', () => {
    const { getByText } = render(
      <MonthGrid
        monthStart={new Date(2026, 4, 1)}
        events={[
          _event({
            entity_id: 'calendar.family',
            summary: 'Spring Break',
            all_day: true,
            // Date-only ISO strings interpret as midnight UTC; for an
            // all-day event May 1 → May 8, May 1 is the only day in
            // this assertion.
            start: new Date(2026, 4, 1).toISOString(),
            end: new Date(2026, 4, 2).toISOString(),
          }),
        ]}
      />,
    )
    expect(getByText('Spring Break')).toBeTruthy()
  })

  it('multi-day all-day event appears under each day in span', () => {
    // May 1 (start) through May 3 (last visible) — a 3-day span uses
    // end = May 4 to match HA's exclusive-end convention.
    const { getAllByText } = render(
      <MonthGrid
        monthStart={new Date(2026, 4, 1)}
        events={[
          _event({
            entity_id: 'calendar.family',
            summary: 'Trip',
            all_day: true,
            start: new Date(2026, 4, 1).toISOString(),
            end: new Date(2026, 4, 4).toISOString(),
          }),
        ]}
      />,
    )
    // Three days × one entry each.
    expect(getAllByText('Trip')).toHaveLength(3)
  })

  it('day with events is clickable when onSelectDate is provided', () => {
    const onSelectDate = vi.fn()
    const { container } = render(
      <MonthGrid
        monthStart={new Date(2026, 4, 1)}
        events={[
          _event({
            entity_id: 'calendar.kid',
            summary: 'Soccer',
            start: new Date(2026, 4, 4, 16, 0).toISOString(),
            end: new Date(2026, 4, 4, 17, 0).toISOString(),
          }),
        ]}
        onSelectDate={onSelectDate}
      />,
    )
    // Click the cell that hosts the Soccer event. The cell is rendered
    // as a button when it has events + onSelect; query it via role+label.
    const cells = container.querySelectorAll('button[role="gridcell"]')
    const soccerCell = Array.from(cells).find((c) =>
      c.textContent?.includes('Soccer'),
    )
    expect(soccerCell).toBeTruthy()
    fireEvent.click(soccerCell!)
    expect(onSelectDate).toHaveBeenCalledTimes(1)
    const arg = onSelectDate.mock.calls[0][0] as Date
    expect(arg.getFullYear()).toBe(2026)
    expect(arg.getMonth()).toBe(4)
    expect(arg.getDate()).toBe(4)
  })

  it('day with no events is not interactive even with onSelectDate set', () => {
    const onSelectDate = vi.fn()
    const { container } = render(
      <MonthGrid
        monthStart={new Date(2026, 4, 1)}
        events={[]}
        onSelectDate={onSelectDate}
      />,
    )
    // No cells should be buttons because no day has events.
    const buttons = container.querySelectorAll('button[role="gridcell"]')
    expect(buttons).toHaveLength(0)
  })

  it('today-cell highlights its day number', () => {
    const today = new Date(2026, 4, 4) // a Monday in this month
    const { container } = render(
      <MonthGrid
        monthStart={new Date(2026, 4, 1)}
        today={today}
        events={[]}
      />,
    )
    // Today's day number should sit inside the brand-600 chip; query
    // for that class.
    const todayChip = container.querySelector('.bg-brand-600')
    expect(todayChip?.textContent?.trim()).toBe('4')
  })

  it('selected date gets a ring outline', () => {
    const selected = new Date(2026, 4, 4)
    const { container } = render(
      <MonthGrid
        monthStart={new Date(2026, 4, 1)}
        selectedDate={selected}
        events={[]}
      />,
    )
    const ringed = container.querySelectorAll('.ring-2')
    expect(ringed.length).toBe(1)
    expect(ringed[0].textContent).toContain('4')
  })
})
