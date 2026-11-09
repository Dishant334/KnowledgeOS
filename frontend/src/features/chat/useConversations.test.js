// Hook tests for useConversations: the sidebar list, an "optimistic" rename that is undone on failure, and delete.
// waitFor(() => expect(...)) retries the check until it passes (or 1 s passes): for results of async work.
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { deleteConversation, listConversations, renameConversation } from '../../api/conversations'
import { useConversations } from './useConversations'

vi.mock('../../api/conversations', () => ({
  listConversations: vi.fn(),
  renameConversation: vi.fn(),
  deleteConversation: vi.fn(),
}))

const rows = [
  { id: 'a', title: 'Leave policy' },
  { id: 'b', title: 'Parking' },
]

afterEach(() => vi.clearAllMocks())

async function loaded() {
  vi.mocked(listConversations).mockResolvedValue(rows)
  const hook = renderHook(() => useConversations())
  await waitFor(() => expect(hook.result.current.conversations).toEqual(rows))
  return hook
}

describe('useConversations', () => {
  it('starts as null (loading), then holds the list', async () => {
    vi.mocked(listConversations).mockResolvedValue(rows)
    const { result } = renderHook(() => useConversations())
    expect(result.current.conversations).toBeNull()
    await waitFor(() => expect(result.current.conversations).toEqual(rows))
  })

  it('a failed load gives an error message', async () => {
    vi.mocked(listConversations).mockRejectedValue(new Error('Cannot reach the server.'))
    const { result } = renderHook(() => useConversations())
    await waitFor(() => expect(result.current.error).toBe('Cannot reach the server.'))
  })

  it('rename shows the new title and keeps the one the backend saved', async () => {
    const { result } = await loaded()
    vi.mocked(renameConversation).mockResolvedValue({ id: 'a', title: 'Holidays' })
    await act(() => result.current.rename('a', 'Holidays'))
    expect(result.current.conversations[0].title).toBe('Holidays')
  })

  it('a refused rename puts the old title back and reports the error', async () => {
    const { result } = await loaded()
    vi.mocked(renameConversation).mockRejectedValue(new Error('Not found.'))

    await act(async () => {
      await expect(result.current.rename('a', 'Holidays')).rejects.toThrow('Not found.')
    })

    expect(result.current.conversations[0].title).toBe('Leave policy')
  })

  it('delete removes the row after the backend confirms', async () => {
    const { result } = await loaded()
    vi.mocked(deleteConversation).mockResolvedValue()
    await act(() => result.current.remove('a'))
    expect(result.current.conversations.map((c) => c.id)).toEqual(['b'])
  })

  it('a chat that is already gone (404) is dropped too', async () => {
    const { result } = await loaded()
    vi.mocked(deleteConversation).mockRejectedValue(Object.assign(new Error('Not found.'), { code: 'not_found' }))
    await act(() => result.current.remove('a'))
    expect(result.current.conversations.map((c) => c.id)).toEqual(['b'])
  })

  it('any other delete failure keeps the row and throws', async () => {
    const { result } = await loaded()
    vi.mocked(deleteConversation).mockRejectedValue(Object.assign(new Error('Server down'), { code: 'server' }))
    await act(async () => {
      await expect(result.current.remove('a')).rejects.toThrow('Server down')
    })
    expect(result.current.conversations).toHaveLength(2)
  })
})
