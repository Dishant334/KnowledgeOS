// Component tests for "What I remember about you" (the memory API is mocked).
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { addMemory, deleteMemory, forgetEverything, listMemories } from '../../api/memory'
import MemoryDialog from './MemoryDialog'

// importOriginal keeps the real constants (MAX_MEMORIES = 15...) and replaces only the network calls.
vi.mock('../../api/memory', async (importOriginal) => ({
  ...(await importOriginal()),
  listMemories: vi.fn(),
  addMemory: vi.fn(),
  deleteMemory: vi.fn(),
  forgetEverything: vi.fn(),
}))

const fact = (id, text, extra = {}) => ({ id, text, created_at: '2026-11-01T10:00:00', source_conversation_id: null, ...extra })

function renderDialog(memories = []) {
  vi.mocked(listMemories).mockResolvedValue(memories)
  const handlers = { onClose: vi.fn(), onOpenConversation: vi.fn() }
  render(<MemoryDialog {...handlers} />)
  return { user: userEvent.setup(), ...handlers }
}

afterEach(() => vi.clearAllMocks())

describe('MemoryDialog', () => {
  it('lists the facts and where each came from', async () => {
    const { user, onOpenConversation } = renderDialog([
      fact('m1', 'Works in the Berlin office'),
      fact('m2', 'Is preparing the onboarding guide', { source_conversation_id: 'c-9' }),
    ])
    expect(await screen.findByText('Works in the Berlin office')).toBeInTheDocument()
    expect(screen.getByText(/added by you/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'learned in a chat' }))
    expect(onOpenConversation).toHaveBeenCalledWith('c-9')
  })

  it('shows the empty state', async () => {
    renderDialog([])
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument()
  })

  it('adds a fact and clears the box', async () => {
    const { user } = renderDialog([])
    vi.mocked(addMemory).mockResolvedValue(fact('m3', 'Prefers short answers'))
    const box = screen.getByRole('textbox', { name: 'Add something to remember' })

    await user.type(box, 'Prefers short answers{Enter}')

    expect(addMemory).toHaveBeenCalledWith('Prefers short answers')
    expect(await screen.findByText('Prefers short answers')).toBeInTheDocument()
    expect(box).toHaveValue('')
  })

  it('shows the backend\'s reason when a fact is refused, and clears it when typing', async () => {
    const { user } = renderDialog([])
    vi.mocked(addMemory).mockRejectedValue(new Error('This looks like sensitive information and was not stored.'))
    const box = screen.getByRole('textbox', { name: 'Add something to remember' })

    await user.type(box, 'my password is hunter2{Enter}')
    expect(await screen.findByText(/sensitive information/)).toBeInTheDocument()

    await user.type(box, '!')
    expect(screen.queryByText(/sensitive information/)).not.toBeInTheDocument()
  })

  it('at 15 facts the box is disabled', async () => {
    renderDialog(Array.from({ length: 15 }, (_, i) => fact(`m${i}`, `Fact ${i}`)))
    await screen.findByText('Fact 0')
    expect(screen.getByRole('textbox', { name: 'Add something to remember' })).toBeDisabled()
    expect(screen.getByText('15 of 15')).toBeInTheDocument()
  })

  it('forgets one fact', async () => {
    const { user } = renderDialog([fact('m1', 'Works in Berlin'), fact('m2', 'Likes tea')])
    vi.mocked(deleteMemory).mockResolvedValue()

    await user.click(await screen.findByRole('button', { name: 'Forget "Works in Berlin"' }))

    expect(deleteMemory).toHaveBeenCalledWith('m1')
    expect(screen.queryByText('Works in Berlin')).not.toBeInTheDocument()
    expect(screen.getByText('Likes tea')).toBeInTheDocument()
  })

  it('"Forget everything" asks first, then clears the list', async () => {
    const { user } = renderDialog([fact('m1', 'Works in Berlin')])
    vi.mocked(forgetEverything).mockResolvedValue()

    await user.click(await screen.findByRole('button', { name: 'Forget everything' }))
    expect(forgetEverything).not.toHaveBeenCalled() // only the confirmation appeared
    expect(screen.getByText('Forget all 1?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Forget everything' }))
    expect(forgetEverything).toHaveBeenCalled()
    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument()
  })

  it('Esc closes it', async () => {
    const { user, onClose } = renderDialog([])
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
