import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteDocument, listDocuments } from '../../api/documents'
import Button from '../../components/Button'
import ErrorBanner from '../../components/ErrorBanner'
import Spinner from '../../components/Spinner'
import { ACCEPT_ATTRIBUTE, IN_PROGRESS, fileTypeLabel, formatBytes, formatDate } from '../../lib/files'
import StatusBadge from './StatusBadge'

const POLL_MS = 3000

// "Your documents": every file you uploaded with its status, an Upload button and delete (asks first).
// A dialog over the chat; Esc, the X or a click outside closes it. While any file is still processing the list
// refreshes by itself, and it also refreshes whenever an upload from the question box changes state (uploadsVersion).
export default function DocumentsPanel({ onClose, onUpload, uploadsVersion }) {
  const [docs, setDocs] = useState(null) // null = not loaded yet
  const [error, setError] = useState(null)
  const [confirming, setConfirming] = useState(null) // id waiting for "Delete?" confirmation
  const [deleting, setDeleting] = useState(null)
  const [deleteError, setDeleteError] = useState(null)
  const fileInput = useRef(null)
  const dialog = useRef(null)

  const load = useCallback(async () => {
    try {
      setDocs(await listDocuments())
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  // first load, and again when an upload changes state (ignored if the panel closed meanwhile)
  useEffect(() => {
    let alive = true
    listDocuments().then(
      (list) => {
        if (!alive) return
        setDocs(list)
        setError(null)
      },
      (e) => alive && setError(e.message),
    )
    return () => {
      alive = false
    }
  }, [uploadsVersion])

  // refresh while something is processing
  const busy = docs?.some((d) => IN_PROGRESS.has(d.status))
  useEffect(() => {
    if (!busy) return
    const timer = setInterval(load, POLL_MS)
    return () => clearInterval(timer)
  }, [busy, load])

  useEffect(() => {
    dialog.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const remove = async (id) => {
    setDeleting(id)
    setDeleteError(null)
    try {
      await deleteDocument(id)
      setDocs((all) => all.filter((d) => d.id !== id))
    } catch (e) {
      setDeleteError(e.code === 'not_found' ? 'That document was already deleted.' : e.message)
      if (e.code === 'not_found') setDocs((all) => all.filter((d) => d.id !== id))
    } finally {
      setDeleting(null)
      setConfirming(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="documents-title"
        className="page-in flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-surface shadow-2xl ring-1 ring-stone-200 focus:outline-none"
      >
        <header className="flex items-center justify-between gap-3 border-b border-stone-200 px-5 py-4">
          <div>
            <h2 id="documents-title" className="font-display text-xl font-semibold text-ink">
              Your documents
            </h2>
            <p className="text-sm text-stone-600">
              {docs ? `${docs.length} ${docs.length === 1 ? 'file' : 'files'}` : 'Loading...'} · answers come only from these
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              ref={fileInput}
              type="file"
              multiple
              accept={ACCEPT_ATTRIBUTE}
              hidden
              onChange={(e) => {
                onUpload(e.target.files)
                e.target.value = ''
              }}
            />
            <Button onClick={() => fileInput.current.click()}>Upload</Button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="grid size-9 place-items-center rounded-lg text-stone-600 transition hover:bg-stone-100 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand-700"
            >
              <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {error && (
            <div className="p-2">
              <ErrorBanner message={error} action={<Button variant="secondary" onClick={load}>Try again</Button>} />
            </div>
          )}
          {deleteError && (
            <div className="p-2">
              <ErrorBanner message={deleteError} />
            </div>
          )}
          {!docs && !error && <Spinner label="Loading your documents..." className="py-16" />}
          {docs?.length === 0 && (
            <div className="px-6 py-14 text-center">
              <p className="font-display text-lg font-semibold text-ink">No documents yet</p>
              <p className="mt-1 text-sm text-stone-600">
                Upload PDF, Word, PowerPoint, Excel, CSV, text, Markdown or HTML files (up to 20 MB each).
              </p>
            </div>
          )}

          <ul className="flex flex-col">
            {docs?.map((d) => (
              <li key={d.id} className="flex items-start gap-3 rounded-xl px-3 py-3 transition hover:bg-stone-50">
                <span className="mt-0.5 w-11 shrink-0 rounded-md bg-stone-100 py-1 text-center text-[10px] font-bold text-stone-700">
                  {fileTypeLabel(d.filename)}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink" title={d.filename}>
                    {d.filename}
                  </p>
                  <p className="mt-0.5 text-xs text-stone-600">
                    {formatBytes(d.file_size)} · {formatDate(d.created_at)}
                  </p>
                  {d.status === 'failed' && d.failure_reason && (
                    <p className="mt-1 text-xs text-red-700 dark:text-red-400">{d.failure_reason}</p>
                  )}
                </div>
                <StatusBadge status={d.status} />
                {confirming === d.id ? (
                  <span className="flex shrink-0 items-center gap-1.5">
                    <Button variant="danger" className="px-2.5 py-1 text-xs" disabled={deleting === d.id} onClick={() => remove(d.id)}>
                      {deleting === d.id ? 'Deleting...' : 'Delete'}
                    </Button>
                    <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={deleting === d.id} onClick={() => setConfirming(null)}>
                      Cancel
                    </Button>
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirming(d.id)}
                    aria-label={`Delete ${d.filename}`}
                    title="Delete"
                    className="grid size-8 shrink-0 place-items-center rounded-lg text-stone-600 transition hover:bg-red-50 hover:text-red-700 focus-visible:outline-2 focus-visible:outline-brand-700 dark:hover:bg-red-950/50 dark:hover:text-red-400"
                  >
                    <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                      <path d="M4 6h12M8 6V4.5h4V6M6 6l.7 9.5h6.6L14 6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
