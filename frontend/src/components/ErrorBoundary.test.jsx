// Component test for ErrorBoundary: a crash below it shows the fallback page instead of a blank screen.
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ErrorBoundary from './ErrorBoundary'

function Boom() {
  throw new Error('secret internal detail')
}

describe('ErrorBoundary', () => {
  it('renders its children when nothing goes wrong', () => {
    render(<ErrorBoundary><p>All good</p></ErrorBoundary>)
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('shows the fallback with a way out, and never the error text', () => {
    // React and our boundary both log the crash; silence the console for this test (restored automatically)
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(<ErrorBoundary><Boom /></ErrorBoundary>)

    expect(screen.getByRole('heading', { name: 'Something went wrong' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reload the page' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to your chats' })).toHaveAttribute('href', '/chat')
    expect(screen.queryByText(/secret internal detail/)).not.toBeInTheDocument()
    expect(log).toHaveBeenCalledWith('KnowledgeOS crashed while rendering:', expect.any(Error), expect.anything())
  })

  it('uses dark mode when the user saved it', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    localStorage.setItem('kos-theme', 'dark')
    const { container } = render(<ErrorBoundary><Boom /></ErrorBoundary>)
    expect(container.firstChild).toHaveClass('dark')
  })
})
