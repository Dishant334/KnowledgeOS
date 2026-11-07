import { useCallback, useEffect, useRef, useState } from 'react'
import { getDocument, listDocuments, uploadDocument } from '../../api/documents'
import { IN_PROGRESS, validateFile } from '../../lib/files'

const POLL_MS = 2500 // how often a processing document is checked
const READY_CHIP_MS = 6000 // a finished chip disappears by itself after this long

// The files being added from the question box. Each item:
//   { key, name, size, status, progress, error, documentId, failureReason, duplicate }
// status: 'uploading' (bytes going up) -> the document's own status 'pending' | 'processing' | 'ready' | 'failed',
//         or 'rejected' (refused before upload) / 'error' (the upload itself failed).
// Files upload ONE AT A TIME (a queue), so a big batch does not burst the backend's hourly upload limit at once and
// every chip gets a clear result. While anything is pending/processing it is re-checked every 2.5 s.
// `version` goes up every time an item's status changes, so other views (the documents panel) know to refresh.
export function useUploads() {
  const [items, setItems] = useState([])
  const [version, setVersion] = useState(0)
  const queue = useRef(Promise.resolve())
  const timers = useRef(new Set())

  const patch = useCallback((key, changes) => {
    setItems((all) => all.map((item) => (item.key === key ? { ...item, ...changes } : item)))
    if ('status' in changes) setVersion((v) => v + 1)
  }, [])

  const remove = useCallback((key) => setItems((all) => all.filter((item) => item.key !== key)), [])

  // a finished chip fades away after a few seconds
  const dismissLater = useCallback(
    (key) => {
      const timer = setTimeout(() => {
        timers.current.delete(timer)
        remove(key)
      }, READY_CHIP_MS)
      timers.current.add(timer)
    },
    [remove],
  )

  const upload = useCallback(
    async (key, file) => {
      // The backend answers a repeated file with the EXISTING document, so note which ids you already had.
      // (Comparing ids, not timestamps: no dependence on clocks or time zones.) If the list fails, just skip the hint.
      let known = null
      try {
        known = new Set((await listDocuments()).map((d) => d.id))
      } catch {
        /* no duplicate hint this time */
      }
      try {
        const doc = await uploadDocument(file, { onProgress: (progress) => patch(key, { progress }) })
        const duplicate = known?.has(doc.id) ?? false
        patch(key, { status: doc.status, progress: 1, documentId: doc.id, failureReason: doc.failure_reason, duplicate })
        if (doc.status === 'ready') dismissLater(key)
      } catch (error) {
        const message =
          error.code === 'rate_limited' && error.retryAfter
            ? `Too many uploads. Try again in ${formatWait(error.retryAfter)}.`
            : error.message || 'The upload failed.'
        patch(key, { status: 'error', error: message })
      }
    },
    [patch, dismissLater],
  )

  const addFiles = useCallback(
    (fileList) => {
      for (const file of fileList) {
        const key = `${file.name}-${file.size}-${Math.random().toString(36).slice(2)}`
        const problem = validateFile(file)
        setItems((all) => [
          ...all,
          { key, name: file.name, size: file.size, status: problem ? 'rejected' : 'uploading', progress: 0, error: problem },
        ])
        if (!problem) queue.current = queue.current.then(() => upload(key, file))
      }
    },
    [upload],
  )

  // keep checking documents that are still being processed
  const waiting = items.filter((item) => IN_PROGRESS.has(item.status) && item.documentId)
  const waitingIds = waiting.map((item) => `${item.key}:${item.documentId}`).join(',')
  useEffect(() => {
    if (!waitingIds) return
    const timer = setInterval(async () => {
      for (const pair of waitingIds.split(',')) {
        const [key, id] = pair.split(':')
        try {
          const doc = await getDocument(id)
          if (!IN_PROGRESS.has(doc.status)) {
            patch(key, { status: doc.status, failureReason: doc.failure_reason })
            if (doc.status === 'ready') dismissLater(key)
          } else {
            patch(key, { status: doc.status })
          }
        } catch (error) {
          if (error.code === 'not_found') patch(key, { status: 'error', error: 'This document was deleted.' })
          // other errors (a blip in the network): try again on the next tick
        }
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [waitingIds, patch, dismissLater])

  // stop the dismiss timers when the chat screen goes away
  useEffect(() => {
    const pending = timers.current
    return () => pending.forEach(clearTimeout)
  }, [])

  return { items, addFiles, remove, version }
}

function formatWait(seconds) {
  if (seconds < 90) return `${seconds} seconds`
  return `${Math.ceil(seconds / 60)} minutes`
}
