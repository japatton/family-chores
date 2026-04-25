import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { BrowseSuggestionsPanel } from './BrowseSuggestionsPanel'
import type { Suggestion } from '../api/types'

// jest-dom matchers like `toBeInTheDocument` aren't installed in this
// workspace — vitest-native assertions only. RTL's getByText/getByRole
// throw when nothing matches, so a successful query is itself an
// assertion of presence; queryByText returning null asserts absence.

function suggestion(over: Partial<Suggestion>): Suggestion {
  return {
    id: 'id-1',
    name: 'Make bed',
    icon: 'mdi:bed-empty',
    category: 'bedroom',
    age_min: 4,
    age_max: null,
    points_suggested: 2,
    default_recurrence_type: 'daily',
    default_recurrence_config: {},
    description: null,
    source: 'starter',
    starter_key: 'make_bed',
    created_at: '2026-04-25T00:00:00',
    updated_at: '2026-04-25T00:00:00',
    ...over,
  }
}

const FIXTURES: Suggestion[] = [
  suggestion({ id: 'a', name: 'Make bed', category: 'bedroom' }),
  suggestion({
    id: 'b',
    name: 'Brush teeth',
    category: 'bathroom',
    age_min: 4,
  }),
  suggestion({
    id: 'c',
    name: 'Walk the dog',
    category: 'pet_care',
    age_min: 8,
  }),
  suggestion({
    id: 'd',
    name: 'Custom thing',
    category: 'other',
    source: 'custom',
    starter_key: null,
  }),
]

describe('BrowseSuggestionsPanel', () => {
  it('renders all suggestions and a heading per occupied category', () => {
    render(<BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />)

    // Each suggestion's name is rendered (getByText throws on miss).
    screen.getByText('Make bed')
    screen.getByText('Brush teeth')
    screen.getByText('Walk the dog')
    screen.getByText('Custom thing')

    // Headings are <h3> — distinct from the category chips (which are
    // <button> elements with the same label text).
    screen.getByRole('heading', { name: 'Bedroom' })
    screen.getByRole('heading', { name: 'Bathroom' })
    screen.getByRole('heading', { name: 'Pet care' })
    screen.getByRole('heading', { name: 'Other' })
  })

  it('filters by search substring (case-insensitive)', async () => {
    const user = userEvent.setup()
    render(<BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />)

    await user.type(screen.getByLabelText('Search suggestions'), 'BED')

    screen.getByText('Make bed')
    expect(screen.queryByText('Brush teeth')).toBeNull()
    expect(screen.queryByText('Walk the dog')).toBeNull()
  })

  it('filters by category chip toggle', async () => {
    const user = userEvent.setup()
    render(<BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'Pet care' }))

    screen.getByText('Walk the dog')
    expect(screen.queryByText('Make bed')).toBeNull()
    expect(screen.queryByText('Brush teeth')).toBeNull()
  })

  it('filters by age (excludes higher age_min)', async () => {
    const user = userEvent.setup()
    render(<BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />)

    await user.type(screen.getByLabelText('Filter by age'), '4')

    screen.getByText('Make bed') // age_min=4 ok
    screen.getByText('Brush teeth') // age_min=4 ok
    expect(screen.queryByText('Walk the dog')).toBeNull() // age_min=8 → excluded
  })

  it('filters by source (custom only) when toggled', async () => {
    const user = userEvent.setup()
    render(<BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />)

    // Source filter sits behind a disclosure — open it first.
    await user.click(screen.getByText('Filter by source'))
    await user.click(
      screen.getByRole('button', { name: 'My suggestions only' }),
    )

    screen.getByText('Custom thing')
    expect(screen.queryByText('Make bed')).toBeNull()
    expect(screen.queryByText('Brush teeth')).toBeNull()
  })

  it('calls onSelect with the tapped suggestion', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(
      <BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={onSelect} />,
    )

    await user.click(screen.getByTestId('suggestion-c'))

    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'c', name: 'Walk the dog' }),
    )
  })

  it('renders an empty state when no suggestions match filters', async () => {
    const user = userEvent.setup()
    render(<BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />)

    await user.type(
      screen.getByLabelText('Search suggestions'),
      'XYZNotMatching',
    )

    expect(screen.getByRole('status').textContent).toMatch(/no suggestions/i)
  })

  it('shows the "Manage my suggestions" link only when onManage is provided', () => {
    const { rerender } = render(
      <BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />,
    )
    expect(
      screen.queryByRole('button', { name: /manage my suggestions/i }),
    ).toBeNull()

    rerender(
      <BrowseSuggestionsPanel
        suggestions={FIXTURES}
        onSelect={() => {}}
        onManage={() => {}}
      />,
    )
    screen.getByRole('button', { name: /manage my suggestions/i })
  })

  it('clear-age button resets to "any" and re-includes higher ages', async () => {
    const user = userEvent.setup()
    render(<BrowseSuggestionsPanel suggestions={FIXTURES} onSelect={() => {}} />)

    // Type 4 into the age input — same path the previous test exercises.
    await user.type(screen.getByLabelText('Filter by age'), '4')
    expect(screen.queryByText('Walk the dog')).toBeNull()

    // The clear button appears as a sibling of the input. Find it via
    // text rather than role — `getByRole('button', { name: 'clear' })`
    // came back empty in JSDOM here even though the button rendered
    // visibly; getByText('clear') resolves it cleanly.
    const clearBtn = screen.getByText('clear', { selector: 'button' })
    await user.click(clearBtn)
    screen.getByText('Walk the dog')
  })
})
