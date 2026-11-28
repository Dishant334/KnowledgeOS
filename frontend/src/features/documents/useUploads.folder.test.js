// Stage 11: useUploads.addFolder: a chosen folder is packed, then goes through the normal upload queue.
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { listDocuments, uploadDocument } from '../../api/documents'
import { packFolder } from '../../lib/zipFolder'
import { useUploads } from './useUploads'

vi.mock('../../api/documents', () => ({
  uploadDocument: vi.fn(),
  listDocuments: vi.fn(),
  getDocument: vi.fn(),
  deleteDocument: vi.fn(),
}))
vi.mock('../../lib/zipFolder', () => ({ packFolder: vi.fn() }))

const getConversationId = vi.fn(async () => 'conv-1')
const folderFile = (path) => Object.defineProperty(new File(['x'], path.split('/').pop()), 'webkitRelativePath', { value: path })
const flush = () => act(() => vi.advanceTimersByTimeAsync(0))

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(listDocuments).mockResolvedValue([])
})
afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('useUploads.addFolder', () => {
  it('shows a packing chip, then uploads the zip with its note', async () => {
    const zip = new File([new Uint8Array(10)], 'proj.zip', { type: 'application/zip' })
    let finish
    vi.mocked(packFolder).mockReturnValue(new Promise((resolve) => (finish = resolve)))
    vi.mocked(uploadDocument).mockResolvedValue({ id: 4, status: 'pending', failure_reason: null })
    const { result } = renderHook(() => useUploads(getConversationId, 'code'))

    act(() => {
      result.current.addFolder([folderFile('proj/a.py')])
    })
    expect(result.current.items).toHaveLength(1)
    expect(result.current.items[0]).toMatchObject({ name: 'proj.zip', status: 'packing' })

    await act(async () => finish({ file: zip, summary: 'Packed 1 file (0.0 MB); none skipped.' }))
    await flush()

    expect(uploadDocument).toHaveBeenCalledWith(zip, expect.objectContaining({ conversationId: 'conv-1' }))
    expect(result.current.items).toHaveLength(1)                       // the packing chip became the upload chip
    expect(result.current.items[0]).toMatchObject({ name: 'proj.zip', documentId: 4, note: 'Packed 1 file (0.0 MB); none skipped.' })
  })

  it('a folder that cannot be packed stays as a red chip with the reason, and nothing is uploaded', async () => {
    vi.mocked(packFolder).mockRejectedValue(new Error('Nothing in this folder can be read (skipped 3).'))
    const { result } = renderHook(() => useUploads(getConversationId, 'code'))
    await act(async () => {
      await result.current.addFolder([folderFile('p/logo.png')])
    })
    expect(result.current.items[0]).toMatchObject({ status: 'rejected', error: 'Nothing in this folder can be read (skipped 3).' })
    expect(uploadDocument).not.toHaveBeenCalled()
  })

  it('does nothing in a Documents chat or for an empty selection', async () => {
    const docs = renderHook(() => useUploads(getConversationId, 'docs'))
    await act(async () => {
      await docs.result.current.addFolder([folderFile('p/a.py')])
    })
    expect(docs.result.current.items).toEqual([])

    const code = renderHook(() => useUploads(getConversationId, 'code'))
    await act(async () => {
      await code.result.current.addFolder([])
    })
    expect(code.result.current.items).toEqual([])
    expect(packFolder).not.toHaveBeenCalled()
  })

  it('a zip picked with the paperclip is queued like any file (a Codebase chat accepts it)', async () => {
    vi.mocked(uploadDocument).mockResolvedValue({ id: 5, status: 'pending', failure_reason: null })
    const zip = { name: 'project.zip', size: 4096 }
    const { result } = renderHook(() => useUploads(getConversationId, 'code'))
    act(() => result.current.addFiles([zip]))
    await flush()
    expect(uploadDocument).toHaveBeenCalledWith(zip, expect.anything())
    expect(result.current.items[0]).toMatchObject({ documentId: 5 })
  })
})
