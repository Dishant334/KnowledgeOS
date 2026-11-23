// Integration tests for the whole chat screen: the real ChatLayout with its real children (sidebar, question box,
// messages, source panel). Only the edges are fake: the API modules (no backend) and Clerk (no login).
// These check that the pieces work TOGETHER, the way a user moves through them.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { askStream } from '../../api/askStream'
import { createConversation, getConversation, listConversationDocuments, listConversations } from '../../api/conversations'
import ThemeProvider from '../../theme/ThemeProvider'
import ChatLayout from './ChatLayout'

vi.mock('@clerk/clerk-react', () => ({ UserButton: () => null }))
vi.mock('../../api/askStream', () => ({ askStream: vi.fn() }))
vi.mock('../../api/documents', () => ({ uploadDocument: vi.fn(), listDocuments: vi.fn(), getDocument: vi.fn(), deleteDocument: vi.fn() }))
vi.mock('../../api/conversations', () => ({
  listConversations: vi.fn(),
  createConversation: vi.fn(),
  getConversation: vi.fn(),
  listConversationDocuments: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
  discardConversation: vi.fn(async () => {}),
  discardConversationOnExit: vi.fn(),
  rememberConversation: vi.fn(),
  rememberConversationOnExit: vi.fn(),
}))

const DONE = {
  answer: 'Employees get 25 vacation days [1].',
  conversation_id: 'c-1',
  abstained: false,
  citations: [{ marker: '[1]', document_id: 7, source_name: 'leave_policy.pdf', page_number: 3, snippet: 'Every employee is entitled to 25 days of paid leave.' }],
}

// Shows the current address, so a test can check where the app navigated.
function Location() {
  return <output aria-label="address">{useLocation().pathname}</output>
}

function renderChat(path = '/chat') {
  render(
    <MemoryRouter initialEntries={[path]}>
      <ThemeProvider>
        <Routes>
          <Route path="/chat" element={<ChatLayout />} />
          <Route path="/chat/:conversationId" element={<ChatLayout />} />
        </Routes>
        <Location />
      </ThemeProvider>
    </MemoryRouter>,
  )
  return userEvent.setup()
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listConversations).mockResolvedValue([])
  vi.mocked(createConversation).mockResolvedValue({ id: 'c-1', title: null })
})

describe('ChatLayout', () => {
  it('asks a question, streams the answer, opens its source and moves to the chat address', async () => {
    let releaseAnswer
    vi.mocked(askStream).mockImplementation(async ({ onToken }) => {
      onToken('Employees get ')
      await new Promise((resolve) => (releaseAnswer = resolve)) // hold the stream open so we can look at it mid-way
      onToken('25 vacation days [1].')
      return DONE
    })
    const user = renderChat()

    await user.type(screen.getByRole('textbox', { name: 'Your question' }), 'How many vacation days?{Enter}')

    // the question appears at once, the first words stream in, and the send button has become Stop.
    // (selector 'p': the question bubble. jsdom ignores CSS, so it also "sees" the phone-only top bar, a <span> that
    // shows the same question as the chat's title. Without the selector the text would match twice.)
    expect(screen.getByText('How many vacation days?', { selector: 'p' })).toBeInTheDocument()
    expect(await screen.findByText(/Employees get/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Stop the answer' })).toBeInTheDocument()
    expect(askStream).toHaveBeenCalledWith(expect.objectContaining({ query: 'How many vacation days?', conversationId: 'c-1' }))

    releaseAnswer()

    // the saved answer, with its citation chip and source button
    await user.click(await screen.findByRole('button', { name: 'Open source 1' }))
    const panel = screen.getByRole('complementary', { name: 'Source 1' })
    expect(within(panel).getByText('leave_policy.pdf')).toBeInTheDocument()
    expect(within(panel).getByText('Page 3')).toBeInTheDocument()
    expect(within(panel).getByText('Every employee is entitled to 25 days of paid leave.')).toBeInTheDocument()

    // the new chat got its own address, and the sidebar list was refreshed
    expect(screen.getByRole('status', { name: 'address' })).toHaveTextContent('/chat/c-1')
    expect(listConversations).toHaveBeenCalledTimes(2)

    // Esc closes the source panel
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('complementary', { name: 'Source 1' })).not.toBeInTheDocument()
  })

  it('Stop keeps what arrived and says it was not saved', async () => {
    vi.mocked(askStream).mockImplementation(({ onToken, signal }) => {
      onToken('Half an')
      // like the real fetch: the call fails with an AbortError when the signal is aborted
      return new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
    })
    const user = renderChat()

    await user.type(screen.getByRole('textbox', { name: 'Your question' }), 'Long question{Enter}')
    await user.click(await screen.findByRole('button', { name: 'Stop the answer' }))

    expect(await screen.findByText('Stopped. This answer was not saved.')).toBeInTheDocument()
    expect(screen.getByText('Half an')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'address' })).toHaveTextContent(/^\/chat$/) // nothing saved: no new address
  })

  it('the question limit (429) says how long to wait, and Retry asks again', async () => {
    vi.mocked(askStream)
      .mockRejectedValueOnce(Object.assign(new Error('Too many'), { code: 'rate_limited', retryAfter: 20, status: 429 }))
      .mockResolvedValueOnce(DONE)
    const user = renderChat()

    await user.type(screen.getByRole('textbox', { name: 'Your question' }), 'Vacation?{Enter}')
    expect(await screen.findByText('Too many questions. Try again in 20 seconds.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText(/Employees get 25 vacation days/)).toBeInTheDocument()
    expect(askStream).toHaveBeenCalledTimes(2)
    expect(vi.mocked(askStream).mock.calls[1][0].query).toBe('Vacation?')
  })

  it('opening /chat/<id> loads its messages, citations and documents', async () => {
    vi.mocked(getConversation).mockResolvedValue({
      id: 'c-7',
      messages: [
        { id: 1, role: 'user', content: 'Where do I park?', citations: [] },
        { id: 2, role: 'assistant', content: 'In garage B [1].', citations: [{ marker: '[1]', document_id: 4, source_name: 'parking.md', snippet: 'Use garage B.' }] },
      ],
    })
    vi.mocked(listConversationDocuments).mockResolvedValue([{ id: 4, filename: 'parking.md', status: 'ready' }])
    renderChat('/chat/c-7')

    expect(await screen.findByText('Where do I park?', { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open source 1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove parking.md from your library/ })).toBeInTheDocument()
    expect(getConversation).toHaveBeenCalledWith('c-7')
  })

  it('an unknown conversation shows a message with a way back', async () => {
    vi.mocked(getConversation).mockRejectedValue(Object.assign(new Error('Not found.'), { code: 'not_found' }))
    vi.mocked(listConversationDocuments).mockResolvedValue([])
    renderChat('/chat/does-not-exist')

    expect(await screen.findByText('This conversation does not exist.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /New chat/ }).length).toBeGreaterThan(0)
  })

  // CODEBASE-FEATURE (Stage 4): the chat's mode ("docs" or "code")
  describe('chat mode', () => {
    it('a new chat is a documents chat by default', async () => {
      vi.mocked(askStream).mockResolvedValue(DONE)
      const user = renderChat()
      expect(screen.getByRole('radio', { name: /Documents/ })).toBeChecked()
      await user.type(screen.getByRole('textbox', { name: 'Your question' }), 'Hello there?{Enter}')
      await screen.findByText(/Employees get/)
      expect(createConversation).toHaveBeenCalledWith('docs')
    })

    it('choosing Codebase creates the conversation in code mode', async () => {
      vi.mocked(askStream).mockResolvedValue(DONE)
      const user = renderChat()
      await user.click(screen.getByRole('radio', { name: /Codebase/ }))
      expect(screen.getByRole('radio', { name: /Codebase/ })).toBeChecked()
      expect(screen.getByRole('heading', { name: 'Ask your codebase' })).toBeInTheDocument()
      await user.type(screen.getByPlaceholderText('Ask about your code...'), 'Where is login handled?{Enter}')
      await screen.findByText(/Employees get/)
      expect(createConversation).toHaveBeenCalledWith('code')
    })

    it('the file picker offers only what the chosen mode accepts', async () => {
      const user = renderChat()
      const picker = () => document.querySelector('input[type=file]')
      expect(picker().accept).toContain('.pdf')
      expect(picker().accept).not.toContain('.py')
      await user.click(screen.getByRole('radio', { name: /Codebase/ }))
      expect(picker().accept).toContain('.py')
      expect(picker().accept).not.toContain('.pdf')
    })

    it('opening a saved code chat shows its mode and does not let it be switched', async () => {
      vi.mocked(getConversation).mockResolvedValue({ id: 'c-9', mode: 'code', messages: [] })
      vi.mocked(listConversationDocuments).mockResolvedValue([])
      renderChat('/chat/c-9')
      expect(await screen.findByRole('radio', { name: /Codebase/ })).toBeChecked()
      expect(screen.getByRole('radio', { name: /Documents/ })).toBeDisabled()
      expect(screen.getByRole('radio', { name: /Codebase/ })).toBeDisabled()
      expect(screen.getByText(/fixed once a chat has started/i)).toBeInTheDocument()
    })

    it('a saved chat from before modes existed opens as a documents chat', async () => {
      vi.mocked(getConversation).mockResolvedValue({ id: 'c-8', messages: [] }) // no "mode" field
      vi.mocked(listConversationDocuments).mockResolvedValue([])
      renderChat('/chat/c-8')
      expect(await screen.findByRole('radio', { name: /Documents/ })).toBeChecked()
    })

    it('New chat goes back to a documents chat', async () => {
      vi.mocked(getConversation).mockResolvedValue({ id: 'c-9', mode: 'code', messages: [] })
      vi.mocked(listConversationDocuments).mockResolvedValue([])
      const user = renderChat('/chat/c-9')
      await screen.findByRole('radio', { name: /Codebase/ })
      await user.click(screen.getAllByRole('button', { name: /New chat/ })[0])
      expect(await screen.findByRole('radio', { name: /Documents/ })).toBeChecked()
      expect(screen.getByRole('radio', { name: /Codebase/ })).toBeEnabled()
    })
  })
})
