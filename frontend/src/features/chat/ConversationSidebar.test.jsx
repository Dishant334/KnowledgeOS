// Component tests for the sidebar: loading/empty/error states, day groups, opening, rename and delete.
// It needs its real surroundings: a router (it has a <Link>) and the theme. Clerk's avatar is mocked away.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ThemeProvider from '../../theme/ThemeProvider'
import ConversationSidebar from './ConversationSidebar'

vi.mock('@clerk/clerk-react', () => ({ UserButton: () => null }))

// "now" is frozen at 10 Nov 2026 12:00 local time. Only Date is faked, so userEvent's own timers keep working.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 10, 10, 12, 0))
})
afterEach(() => vi.useRealTimers())

const daysAgo = (days) => new Date(2026, 10, 10 - days, 9, 0).toISOString().replace('Z', '') // zone-less, like the backend

function renderSidebar(props = {}) {
  const handlers = { onSelect: vi.fn(), onNewChat: vi.fn(), onRename: vi.fn(), onDelete: vi.fn(async () => {}), onRetry: vi.fn(), onOpenMemory: vi.fn() }
  render(
    <MemoryRouter>
      <ThemeProvider>
        <ConversationSidebar open={false} onClose={() => {}} activeId={null} conversations={[]} error={null} {...handlers} {...props} />
      </ThemeProvider>
    </MemoryRouter>,
  )
  return { user: userEvent.setup(), ...handlers }
}

describe('ConversationSidebar', () => {
  it('shows placeholder rows while loading', () => {
    renderSidebar({ conversations: null })
    expect(screen.getByRole('list', { name: 'Loading conversations' })).toBeInTheDocument()
  })

  it('says so when there are no conversations', () => {
    renderSidebar({ conversations: [] })
    expect(screen.getByText(/No conversations yet/)).toBeInTheDocument()
  })

  it('a failed load offers Try again', async () => {
    const { user, onRetry } = renderSidebar({ conversations: null, error: 'Cannot reach the server.' })
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(onRetry).toHaveBeenCalled()
  })

  it('groups chats by the day of their newest message', () => {
    renderSidebar({
      conversations: [
        { id: '1', title: 'This morning', last_message_at: daysAgo(0) },
        { id: '2', title: 'Last night', last_message_at: daysAgo(1) },
        { id: '3', title: 'Monday', last_message_at: daysAgo(4) },
        { id: '4', title: 'Last month', last_message_at: daysAgo(20) },
        { id: '5', title: 'Ancient', last_message_at: daysAgo(90) },
      ],
    })
    // each group is a <section> with an <h2>; within() limits the search to one part of the page
    const groupOf = (title) => screen.getByRole('button', { name: title }).closest('section').querySelector('h2').textContent
    expect(groupOf('This morning')).toBe('Today')
    expect(groupOf('Last night')).toBe('Yesterday')
    expect(groupOf('Monday')).toBe('Previous 7 days')
    expect(groupOf('Last month')).toBe('Previous 30 days')
    expect(groupOf('Ancient')).toBe('Older')
  })

  it('an untitled chat is shown as "Untitled chat", the open chat is marked', () => {
    renderSidebar({ activeId: '1', conversations: [{ id: '1', title: null, last_message_at: daysAgo(0) }] })
    expect(screen.getByRole('button', { name: 'Untitled chat' })).toHaveAttribute('aria-current', 'page')
  })

  it('clicking a chat opens it; the pencil asks to rename it', async () => {
    const chat = { id: '1', title: 'Leave policy', last_message_at: daysAgo(0) }
    const { user, onSelect, onRename } = renderSidebar({ conversations: [chat] })

    await user.click(screen.getByRole('button', { name: 'Leave policy' }))
    expect(onSelect).toHaveBeenCalledWith('1')

    await user.click(screen.getByRole('button', { name: 'Rename "Leave policy"' }))
    expect(onRename).toHaveBeenCalledWith(chat)
  })

  it('delete asks first; Cancel keeps the chat', async () => {
    const { user, onDelete } = renderSidebar({ conversations: [{ id: '1', title: 'Leave policy', last_message_at: daysAgo(0) }] })

    await user.click(screen.getByRole('button', { name: 'Delete "Leave policy"' }))
    const confirm = screen.getByText('Delete "Leave policy"?').closest('li')
    await user.click(within(confirm).getByRole('button', { name: 'Cancel' }))

    expect(onDelete).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Leave policy' })).toBeInTheDocument()
  })

  it('confirming deletes it; a failure is shown on the row', async () => {
    const onDelete = vi.fn(async () => Promise.reject(new Error('Server down')))
    const { user } = renderSidebar({ onDelete, conversations: [{ id: '1', title: 'Leave policy', last_message_at: daysAgo(0) }] })

    await user.click(screen.getByRole('button', { name: 'Delete "Leave policy"' }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(onDelete).toHaveBeenCalledWith('1')
    expect(await screen.findByText('Server down')).toBeInTheDocument()
  })
})
