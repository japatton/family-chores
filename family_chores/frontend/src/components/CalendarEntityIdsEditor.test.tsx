import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CalendarEntityIdsEditor } from './CalendarEntityIdsEditor'

describe('CalendarEntityIdsEditor', () => {
  it('renders the existing chips', () => {
    const { getByText } = render(
      <CalendarEntityIdsEditor
        value={['calendar.alice', 'calendar.school']}
        onChange={vi.fn()}
      />,
    )
    expect(getByText('calendar.alice')).toBeTruthy()
    expect(getByText('calendar.school')).toBeTruthy()
  })

  it('calls onChange with the entity removed when × is clicked', () => {
    const onChange = vi.fn()
    const { getByLabelText } = render(
      <CalendarEntityIdsEditor
        value={['calendar.alice', 'calendar.school']}
        onChange={onChange}
      />,
    )
    fireEvent.click(getByLabelText('Remove calendar.alice'))
    expect(onChange).toHaveBeenCalledWith(['calendar.school'])
  })

  it('adds a new entity via the Add button', () => {
    const onChange = vi.fn()
    const { getByPlaceholderText, getByText } = render(
      <CalendarEntityIdsEditor value={['calendar.alice']} onChange={onChange} />,
    )
    const input = getByPlaceholderText(/calendar\./)
    fireEvent.change(input, { target: { value: 'calendar.school' } })
    fireEvent.click(getByText('Add'))
    expect(onChange).toHaveBeenCalledWith(['calendar.alice', 'calendar.school'])
  })

  it('adds via Enter key', () => {
    const onChange = vi.fn()
    const { getByPlaceholderText } = render(
      <CalendarEntityIdsEditor value={[]} onChange={onChange} />,
    )
    const input = getByPlaceholderText(/calendar\./)
    fireEvent.change(input, { target: { value: 'calendar.fresh' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith(['calendar.fresh'])
  })

  it('rejects entity ids that don\'t start with calendar.', () => {
    const onChange = vi.fn()
    const { getByPlaceholderText, getByText, getByRole } = render(
      <CalendarEntityIdsEditor value={[]} onChange={onChange} />,
    )
    const input = getByPlaceholderText(/calendar\./)
    fireEvent.change(input, { target: { value: 'sensor.kitchen' } })
    fireEvent.click(getByText('Add'))
    expect(onChange).not.toHaveBeenCalled()
    expect(getByRole('alert').textContent).toMatch(/calendar\./i)
  })

  it('rejects duplicates', () => {
    const onChange = vi.fn()
    const { getByPlaceholderText, getByText, getByRole } = render(
      <CalendarEntityIdsEditor
        value={['calendar.alice']}
        onChange={onChange}
      />,
    )
    const input = getByPlaceholderText(/calendar\./)
    fireEvent.change(input, { target: { value: 'calendar.alice' } })
    fireEvent.click(getByText('Add'))
    expect(onChange).not.toHaveBeenCalled()
    expect(getByRole('alert').textContent).toMatch(/already in the list/i)
  })

  it('trims whitespace before adding', () => {
    const onChange = vi.fn()
    const { getByPlaceholderText, getByText } = render(
      <CalendarEntityIdsEditor value={[]} onChange={onChange} />,
    )
    const input = getByPlaceholderText(/calendar\./)
    fireEvent.change(input, { target: { value: '  calendar.padded  ' } })
    fireEvent.click(getByText('Add'))
    expect(onChange).toHaveBeenCalledWith(['calendar.padded'])
  })

  it('disabled prop disables Add and × buttons', () => {
    const onChange = vi.fn()
    const { getByText, getByLabelText } = render(
      <CalendarEntityIdsEditor
        value={['calendar.alice']}
        onChange={onChange}
        disabled
      />,
    )
    const addButton = getByText('Add') as HTMLButtonElement
    expect(addButton.disabled).toBe(true)
    const removeButton = getByLabelText('Remove calendar.alice') as HTMLButtonElement
    expect(removeButton.disabled).toBe(true)
  })
})
