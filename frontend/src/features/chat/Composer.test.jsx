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

// CODEBASE-FEATURE (Stage 11): a code chat can take a whole folder
describe('Composer in a Codebase chat', () => {
  const uploads = () => ({ items: [], addFiles: vi.fn(), addFolder: vi.fn() })

  it('offers "Choose a project folder" and the zip hint only in a Codebase chat', () => {
    const { rerender } = render(<Composer value="" onChange={() => {}} onSubmit={() => {}} uploads={uploads()} mode="code" />)
    expect(screen.getByRole('button', { name: 'Choose a project folder' })).toBeInTheDocument()
    expect(screen.getByText(/a \.zip/)).toBeInTheDocument()

    rerender(<Composer value="" onChange={() => {}} onSubmit={() => {}} uploads={uploads()} mode="docs" />)
    expect(screen.queryByRole('button', { name: 'Choose a project folder' })).not.toBeInTheDocument()
    expect(screen.getByText('Answers come only from your uploaded documents.')).toBeInTheDocument()
  })

  it('the folder picker hands its files to addFolder, and the file picker to addFiles', async () => {
    const user = userEvent.setup({ applyAccept: false })
    const up = uploads()
    render(<Composer value="" onChange={() => {}} onSubmit={() => {}} uploads={up} mode="code" />)

    const a = new File(['x = 1'], 'a.py')
    await user.upload(screen.getByTestId('folder-input'), [a])
    expect(up.addFolder).toHaveBeenCalledTimes(1)
    expect(Array.from(up.addFolder.mock.calls[0][0])).toEqual([a])
    expect(up.addFiles).not.toHaveBeenCalled()
  })

  it('the folder input is a directory picker and the file input accepts .zip', () => {
    const { container } = render(<Composer value="" onChange={() => {}} onSubmit={() => {}} uploads={uploads()} mode="code" />)
    expect(screen.getByTestId('folder-input')).toHaveAttribute('webkitdirectory')
    expect(container.querySelector('input[type=file][accept]').getAttribute('accept')).toContain('.zip')
  })
})
