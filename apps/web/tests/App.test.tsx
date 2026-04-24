import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from '../src/App'

describe('App', () => {
  it('renders the coming-soon placeholder', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /family chores/i })).toBeTruthy()
    expect(screen.getByText(/coming soon/i)).toBeTruthy()
  })

  it('links to the repository', () => {
    render(<App />)
    const link = screen.getByRole('link', { name: /repository/i })
    expect(link.getAttribute('href')).toContain('github.com')
  })
})
