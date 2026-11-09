// Component tests for the rename dialog, including an async save that fails.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import RenameDialog from './RenameDialog'

const setup = (props = {}) => {
  const handlers = { onSave: vi.fn(async () => {}), onClose: vi.fn(), ...props }
  render(<RenameDialog currentTitle="Leave policy" {...handlers} />)
  return { user: userEvent.setup(), input: screen.getByRole('textbox', { name: 'Name' }), ...handlers }
}

describe('RenameDialog', () => {
  it('opens with the current name filled in and focused', () => {
    const { input } = setup()
    expect(screen.getByRole('dialog', { name: 'Rename chat' })).toBeInTheDocument()
    expect(input).toHaveValue('Leave policy')
    expect(input).toHaveFocus()
  })

  it('Enter saves the new, trimmed name and closes', async () => {
    const { user, input, onSave, onClose } = setup()
    await user.clear(input)
    await user.type(input, '  Holiday rules  {Enter}')
    expect(onSave).toHaveBeenCalledWith('Holiday rules')
    expect(onClose).toHaveBeenCalled()
  })

  it('an empty name cannot be saved', async () => {
    const { user, input, onSave } = setup()
    await user.clear(input)
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(screen.getByText('The name cannot be empty.')).toBeInTheDocument()
    await user.type(input, '{Enter}')
    expect(onSave).not.toHaveBeenCalled()
  })

  it('an unchanged name just closes, without calling the backend', async () => {
    const { user, onSave, onClose } = setup()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSave).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('Esc closes without saving', async () => {
    const { user, onSave, onClose } = setup()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
    expect(onSave).not.toHaveBeenCalled()
  })

  it('a failed save stays open and shows the reason', async () => {
    const { user, input, onClose } = setup({ onSave: vi.fn(async () => Promise.reject(new Error('Not found.'))) })
    await user.clear(input)
    await user.type(input, 'New name{Enter}')
    // findBy... WAITS (up to 1 s) for the element: use it for anything that appears after an async step
    expect(await screen.findByText('Not found.')).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
  })
})
