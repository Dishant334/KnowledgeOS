// Component tests for the question box.
// Composer is "controlled": the parent owns the text (value + onChange). A tiny wrapper with useState plays the
// parent here, so typing really changes the box like in the app.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import Composer from './Composer'

function Harness({ onSubmit = () => {}, busy = false, onStop = () => {}, initial = '' }) {
  const [value, setValue] = useState(initial)
  return <Composer value={value} onChange={setValue} onSubmit={onSubmit} busy={busy} onStop={onStop} />
}

describe('Composer', () => {
  it('Enter sends the trimmed question', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Harness onSubmit={onSubmit} />)

    await user.type(screen.getByRole('textbox', { name: 'Your question' }), '  How many days?  {Enter}')

    expect(onSubmit).toHaveBeenCalledWith('How many days?')
  })

  it('Shift+Enter starts a new line instead of sending', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Harness onSubmit={onSubmit} />)
    const box = screen.getByRole('textbox', { name: 'Your question' })

    await user.type(box, 'line one{Shift>}{Enter}{/Shift}line two')

    expect(onSubmit).not.toHaveBeenCalled()
    expect(box).toHaveValue('line one\nline two')
  })

  it('the send button is disabled while the box is empty or only spaces', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const send = screen.getByRole('button', { name: 'Send question' })
    expect(send).toBeDisabled()

    await user.type(screen.getByRole('textbox'), '   ')
    expect(send).toBeDisabled()

    await user.type(screen.getByRole('textbox'), 'hi')
    expect(send).toBeEnabled()
  })

  it('clicking send submits', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<Harness onSubmit={onSubmit} initial="Vacation policy?" />)
    await user.click(screen.getByRole('button', { name: 'Send question' }))
    expect(onSubmit).toHaveBeenCalledWith('Vacation policy?')
  })

  it('while an answer is being written: a Stop button, and Enter does not send', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    const onStop = vi.fn()
    render(<Harness busy onSubmit={onSubmit} onStop={onStop} initial="next question" />)

    expect(screen.queryByRole('button', { name: 'Send question' })).not.toBeInTheDocument()
    await user.type(screen.getByRole('textbox'), '{Enter}')
    expect(onSubmit).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Stop the answer' }))
    expect(onStop).toHaveBeenCalledTimes(1)
  })
})
