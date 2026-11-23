// CODEBASE-FEATURE (Stage 4): the new-chat screen with its two mode cards.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import EmptyChat from './EmptyChat'

const renderEmpty = (props = {}) => {
  const onModeChange = vi.fn()
  render(<EmptyChat composer={<div>the question box</div>} mode="docs" onModeChange={onModeChange} locked={false} {...props} />)
  return onModeChange
}

describe('EmptyChat', () => {
  it('offers two modes and shows the chosen one', () => {
    renderEmpty()
    expect(screen.getByRole('radiogroup')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Documents/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Codebase/ })).not.toBeChecked()
    expect(screen.getByText('the question box')).toBeInTheDocument()
  })

  it('tells the parent which mode was picked', async () => {
    const onModeChange = renderEmpty()
    await userEvent.click(screen.getByRole('radio', { name: /Codebase/ }))
    expect(onModeChange).toHaveBeenCalledWith('code')
  })

  it('the heading and help follow the mode', () => {
    renderEmpty({ mode: 'code' })
    expect(screen.getByRole('heading', { name: 'Ask your codebase' })).toBeInTheDocument()
    expect(screen.getByText(/exact file and lines/i)).toBeInTheDocument()
  })

  it('documents mode keeps the original heading and help', () => {
    renderEmpty({ mode: 'docs' })
    expect(screen.getByRole('heading', { name: 'Ask your documents' })).toBeInTheDocument()
    expect(screen.getByText(/exact passage/i)).toBeInTheDocument()
  })

  it('once the chat has started the cards cannot be changed and say why', async () => {
    const onModeChange = renderEmpty({ mode: 'code', locked: true })
    expect(screen.getByRole('radio', { name: /Codebase/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Documents/ })).toBeDisabled()
    await userEvent.click(screen.getByRole('radio', { name: /Documents/ }))
    expect(onModeChange).not.toHaveBeenCalled()
    expect(screen.getByText(/fixed once a chat has started/i)).toBeInTheDocument()
  })

  it('is unlocked and silent about locking in a new chat', () => {
    renderEmpty()
    expect(screen.queryByText(/fixed once a chat has started/i)).toBeNull()
    expect(screen.getByRole('radio', { name: /Codebase/ })).toBeEnabled()
  })
})
