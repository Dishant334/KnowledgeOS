import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteDocument, getDocument, listDocuments, uploadDocument } from '../../api/documents'
import { IN_PROGRESS, validateFile } from '../../lib/files'

const POLL_MS = 2500 // how often a processing document is checked

// The files being added from the question box. Each item:
//   { key, name, size, status, progress, error, documentId, failureReason, duplicate }
// status: 'uploading' (bytes going up) -> the document's own status 'pending' | 'processing' | 'ready' | 'failed',
//         or 'rejected' (refused before upload) / 'error' (the upload itself failed).
// Files upload ONE AT A TIME (a queue), so a big batch does not burst the backend's hourly upload limit at once and
// every chip gets a clear result. While anything is pending/processing it is re-checked every 2.5 s. A finished file
// stays in the list (shown as a plain name chip).
// discard(key) = the chip's X: it DELETES the document from the library (or cancels an upload that is queued or still
// sending). reset() = a new chat: the list starts empty again (documents stay in the library).
// getConversationId(): async, returns the id of the conversation the files belong to (ChatLayout creates it on the
// first upload of a new chat). Every upload is attached to it.
export function useUploads(getConversationId) {
  const [items, setItems] = useState([])
  const queue = useRef(Promise.resolve())
  const controllers = useRef(new Map()) // key -> AbortController of the upload in flight
  const cancelled = useRef(new Set()) // keys the user removed before their upload finished
  const itemsRef = useRef(items)
  useEffect(() => {
    itemsRef.current = items
  }, [items])

  const patch = useCallback((key, changes) => {
    setItems((all) => all.map((item) => (item.key === key ? { ...item, ...changes } : item)))
  }, [])

  const remove = useCallback((key) => setItems((all) => all.filter((item) => item.key !== key)), [])

  const upload = useCallback(
    async (key, file) => {
      if (cancelled.current.has(key)) return // removed while waiting in the queue
      // The backend answers a repeated file with the EXISTING document, so note which ids you already had.
      // (Comparing ids, not timestamps: no dependence on clocks or time zones.) If the list fails, just skip the hint.
      let known = null
      try {
        known = new Set((await listDocuments()).map((d) => d.id))
      } catch {
        /* no duplicate hint this time */
      }
      const controller = new AbortController()
      controllers.current.set(key, controller)
      try {
        const conversationId = await getConversationId()
        if (cancelled.current.has(key)) return
        const doc = await uploadDocument(file, {
          conversationId,
          signal: controller.signal,
          onProgress: (progress) => patch(key, { progress }),
        })
        const duplicate = known?.has(doc.id) ?? false
        if (cancelled.current.has(key)) {
          // removed in the last moment, after the bytes had already arrived: undo it (unless it was an older document)
          if (!duplicate) deleteDocument(doc.id).catch(() => {})
          return
        }
        patch(key, { status: doc.status, progress: 1, documentId: doc.id, failureReason: doc.failure_reason, duplicate })
      } catch (error) {
        if (controller.signal.aborted || cancelled.current.has(key)) return // cancelled by the user
        const message =
          error.code === 'rate_limited' && error.retryAfter
            ? `Too many uploads. Try again in ${formatWait(error.retryAfter)}.`
            : error.message || 'The upload failed.'
        patch(key, { status: 'error', error: message })
      } finally {
        controllers.current.delete(key)
      }
    },
    [patch, getConversationId],
  )

  // The chip's X.
  const discard = useCallback(
    async (key) => {
      const item = itemsRef.current.find((i) => i.key === key)
      if (!item) return
      if (!item.documentId) {
        // never reached the library (refused, failed to upload) or still on its way: cancel and forget it
        cancelled.current.add(key)
        controllers.current.get(key)?.abort()
        remove(key)
        return
      }
      patch(key, { status: 'deleting' })
      try {
        await deleteDocument(item.documentId)
        remove(key)
      } catch (error) {
        if (error.code === 'not_found') remove(key)
        else patch(key, { status: 'error', error: `Could not remove it: ${error.message}` })
      }
    },
    [patch, remove],
  )

  // Opening a saved chat: its documents, shown like finished uploads (or still processing / failed).
  const showExisting = useCallback((documents) => {
    for (const item of itemsRef.current) cancelled.current.add(item.key)
    setItems(
      documents.map((d) => ({
        key: `doc-${d.id}`,
        name: d.filename,
        size: d.file_size,
        status: d.status,
        progress: 1,
        documentId: d.id,
        failureReason: d.failure_reason,
      })),
    )
  }, [])

  // A new chat: an empty list. Uploads still being sent finish in the background and stay in the library.
  const reset = useCallback(() => {
    for (const item of itemsRef.current) cancelled.current.add(item.key)
    setItems([])
  }, [])

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
  }, [waitingIds, patch])

  return { items, addFiles, discard, reset, showExisting }
}

function formatWait(seconds) {
  if (seconds < 90) return `${seconds} seconds`
  return `${Math.ceil(seconds / 60)} minutes`
}
