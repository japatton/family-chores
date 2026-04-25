import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ManageSuggestionsView } from './ManageSuggestionsView'
import type { Suggestion } from '../api/types'

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
  suggestion({
    id: 'c1',
    name: 'Wash car',
    source: 'custom',
    starter_key: null,
  }),
  suggestion({
    id: 'c2',
    name: 'Iron clothes',
    source: 'custom',
    starter_key: null,
  }),
  suggestion({ id: 's1', name: 'Make bed', source: 'starter' }),
  suggestion({ id: 's2', name: 'Brush teeth', source: 'starter' }),
]

beforeEach(() => {
  // The view uses window.confirm() for delete + reset. Auto-accept by
  // default; tests that need to refuse override per-test.
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('ManageSuggestionsView', () => {
  it('renders custom suggestions in the "Your suggestions" section', () => {
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    screen.getByRole('heading', { name: /your suggestions/i })
    screen.getByText('Wash car')
    screen.getByText('Iron clothes')
  })

  it('lists starter suggestions inside the collapsed section', () => {
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    // Disclosure heading is present (with count)
    screen.getByText(/Starter suggestions \(2\)/)
  })

  it('shows an empty-state hint when no custom suggestions exist', () => {
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES.filter((s) => s.source === 'starter')}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    expect(
      screen.getByText(/haven.t created any custom suggestions yet/i),
    ).toBeTruthy()
  })

  it('Edit button reveals a draft form pre-filled with the suggestion', async () => {
    const user = userEvent.setup()
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    // The first custom suggestion is "Wash car" — find its Edit button.
    const editButtons = screen.getAllByRole('button', { name: 'Edit' })
    await user.click(editButtons[0])

    const draft = screen.getByTestId('edit-c1')
    const nameInput = draft.querySelector('input') as HTMLInputElement
    expect(nameInput.value).toBe('Wash car')
  })

  it('Save calls onUpdate with the edited fields', async () => {
    const user = userEvent.setup()
    const onUpdate = vi.fn().mockResolvedValue(undefined)
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={onUpdate}
        onDelete={vi.fn()}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    await user.click(screen.getAllByRole('button', { name: 'Edit' })[0])
    const draft = screen.getByTestId('edit-c1')
    const nameInput = draft.querySelector('input') as HTMLInputElement
    await user.clear(nameInput)
    await user.type(nameInput, 'Wax car')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(onUpdate).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({ name: 'Wax car' }),
    )
  })

  it('Delete on a custom suggestion confirms then calls onDelete', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn().mockResolvedValue(undefined)
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={onDelete}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    await user.click(screen.getAllByRole('button', { name: 'Delete' })[0])

    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onDelete).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'c1', source: 'custom' }),
    )
  })

  it('Hide on a starter suggestion uses the soft-delete confirmation copy', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn().mockResolvedValue(undefined)
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={onDelete}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    // Open the starter disclosure first.
    await user.click(screen.getByText(/Starter suggestions/))
    const hideButtons = screen.getAllByRole('button', { name: 'Hide' })
    await user.click(hideButtons[0])

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringMatching(/restore it later/i))
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onDelete).toHaveBeenCalledWith(
      expect.objectContaining({ id: 's1', source: 'starter' }),
    )
  })

  it('Refusing the confirm dialog skips the delete', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    const onDelete = vi.fn()
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={onDelete}
        onReset={vi.fn()}
        onBack={vi.fn()}
      />,
    )

    await user.click(screen.getAllByRole('button', { name: 'Delete' })[0])
    expect(onDelete).not.toHaveBeenCalled()
  })

  it('Reset button confirms then calls onReset', async () => {
    const user = userEvent.setup()
    const onReset = vi.fn().mockResolvedValue({
      suppressions_cleared: 1,
      seeded: 1,
    })
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onReset={onReset}
        onBack={vi.fn()}
      />,
    )

    await user.click(
      screen.getByRole('button', { name: /reset starter suggestions/i }),
    )

    expect(onReset).toHaveBeenCalledTimes(1)
  })

  it('Back button calls onBack', async () => {
    const user = userEvent.setup()
    const onBack = vi.fn()
    render(
      <ManageSuggestionsView
        suggestions={FIXTURES}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        onReset={vi.fn()}
        onBack={onBack}
      />,
    )

    await user.click(screen.getByRole('button', { name: /back to browse/i }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})
