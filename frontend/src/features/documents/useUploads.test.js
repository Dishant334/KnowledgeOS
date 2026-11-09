// Hook tests for useUploads: the upload queue, polling while a document is processed, duplicates, errors and the X.
//
// renderHook(() => useUploads(...)) runs the hook inside a hidden test component; `result.current` is its latest value.
// act(...) wraps anything that changes React state, so every update is applied before the checks.
// The API module is mocked, and FAKE TIMERS let a test jump 2.5 s ahead instantly instead of really waiting.
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { deleteDocument, getDocument, listDocuments, uploadDocument } from '../../api/documents'
import { useUploads } from './useUploads'

vi.mock('../../api/documents', () => ({
  uploadDocument: vi.fn(),
  listDocuments: vi.fn(),
  getDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))

const pdf = { name: 'policy.pdf', size: 2048 }
const getConversationId = vi.fn(async () => 'conv-1')

// Let every pending promise and timer that is due run (inside act, so React applies the resulting updates).
const flush = (ms = 0) => act(() => vi.advanceTimersByTimeAsync(ms))

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(listDocuments).mockResolvedValue([])
  vi.mocked(deleteDocument).mockResolvedValue()
})
afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useUploads', () => {
  it('uploads into the conversation, then polls until the document is ready', async () => {
    vi.mocked(uploadDocument).mockResolvedValue({ id: 9, status: 'pending', failure_reason: null })
    vi.mocked(getDocument).mockResolvedValueOnce({ id: 9, status: 'processing' }).mockResolvedValueOnce({ id: 9, status: 'ready' })
    const { result } = renderHook(() => useUploads(getConversationId))

    act(() => result.current.addFiles([pdf]))
    expect(result.current.items[0]).toMatchObject({ name: 'policy.pdf', status: 'uploading' })

    await flush()
    expect(uploadDocument).toHaveBeenCalledWith(pdf, expect.objectContaining({ conversationId: 'conv-1' }))
    expect(result.current.items[0]).toMatchObject({ status: 'pending', documentId: 9 })

    await flush(2500) // first check
    expect(result.current.items[0].status).toBe('processing')
    await flush(2500) // second check
    expect(result.current.items[0].status).toBe('ready')

    await flush(10000) // finished documents are not checked any more
    expect(getDocument).toHaveBeenCalledTimes(2)
  })

  it('refuses an unsupported file without uploading it', async () => {
    const { result } = renderHook(() => useUploads(getConversationId))
    act(() => result.current.addFiles([{ name: 'photo.png', size: 10 }]))
    await flush()
    expect(result.current.items[0]).toMatchObject({ status: 'rejected', error: expect.stringMatching(/not supported/) })
    expect(uploadDocument).not.toHaveBeenCalled()
  })

  it('uploads one file at a time', async () => {
    let finishFirst
    vi.mocked(uploadDocument)
      .mockImplementationOnce(() => new Promise((resolve) => (finishFirst = () => resolve({ id: 1, status: 'ready' }))))
      .mockResolvedValueOnce({ id: 2, status: 'ready' })
    const { result } = renderHook(() => useUploads(getConversationId))

    act(() => result.current.addFiles([pdf, { name: 'notes.md', size: 10 }]))
    await flush()
    expect(uploadDocument).toHaveBeenCalledTimes(1) // the second waits in the queue

    finishFirst()
    await flush()
    expect(uploadDocument).toHaveBeenCalledTimes(2)
    expect(result.current.items.map((i) => i.status)).toEqual(['ready', 'ready'])
  })

  it('marks a file you already had as a duplicate', async () => {
    vi.mocked(listDocuments).mockResolvedValue([{ id: 5 }])
    vi.mocked(uploadDocument).mockResolvedValue({ id: 5, status: 'ready' })
    const { result } = renderHook(() => useUploads(getConversationId))
    act(() => result.current.addFiles([pdf]))
    await flush()
    expect(result.current.items[0].duplicate).toBe(true)
  })

  it('the upload limit (429) says how long to wait', async () => {
    vi.mocked(uploadDocument).mockRejectedValue(Object.assign(new Error('Too many'), { code: 'rate_limited', retryAfter: 30 }))
    const { result } = renderHook(() => useUploads(getConversationId))
    act(() => result.current.addFiles([pdf]))
    await flush()
    expect(result.current.items[0]).toMatchObject({ status: 'error', error: 'Too many uploads. Try again in 30 seconds.' })
  })

  it('the X on a finished document deletes it from the library', async () => {
    vi.mocked(uploadDocument).mockResolvedValue({ id: 9, status: 'ready' })
    const { result } = renderHook(() => useUploads(getConversationId))
    act(() => result.current.addFiles([pdf]))
    await flush()

    await act(() => result.current.discard(result.current.items[0].key))

    expect(deleteDocument).toHaveBeenCalledWith(9)
    expect(result.current.items).toEqual([])
  })

  it('a failed delete keeps the chip with the reason', async () => {
    vi.mocked(uploadDocument).mockResolvedValue({ id: 9, status: 'ready' })
    vi.mocked(deleteDocument).mockRejectedValue(Object.assign(new Error('Server down'), { code: 'server' }))
    const { result } = renderHook(() => useUploads(getConversationId))
    act(() => result.current.addFiles([pdf]))
    await flush()

    await act(() => result.current.discard(result.current.items[0].key))

    expect(result.current.items[0]).toMatchObject({ status: 'error', error: 'Could not remove it: Server down' })
  })

  it('showExisting lists a saved chat\'s documents and polls the ones still processing', async () => {
    vi.mocked(getDocument).mockResolvedValue({ id: 4, status: 'ready' })
    const { result } = renderHook(() => useUploads(getConversationId))

    act(() =>
      result.current.showExisting([
        { id: 3, filename: 'a.pdf', status: 'ready' },
        { id: 4, filename: 'b.pdf', status: 'processing' },
      ]),
    )
    await flush(2500)

    expect(getDocument).toHaveBeenCalledWith('4')
    expect(result.current.items.map((i) => [i.name, i.status])).toEqual([['a.pdf', 'ready'], ['b.pdf', 'ready']])
  })
})
