import { useCallback, useEffect, useRef, useState } from 'react'
import { MAX_MEMORIES, MAX_MEMORY_CHARS, addMemory, deleteMemory, forgetEverything, listMemories } from '../../api/memory'
import Button from '../../components/Button'
import ErrorBanner from '../../components/ErrorBanner'
import Spinner from '../../components/Spinner'
import { formatDate } from '../../lib/files'

// "What I remember about you": the facts every conversation gets as background. They are learned from long chats
// (role, office, preferences, ongoing projects; never secrets) or added here by hand. Delete one with its bin, or
// all of them with "Forget everything" (asks first). A learned fact links to the chat it came from.
// Facts are plain text from the user or the model: always shown as text, never as HTML.
export default function MemoryDialog({ onClose, onOpenConversation }) {
  const [memories, setMemories] = useState(null) // null = loading
  const [loadError, setLoadError] = useState(null)
  const [text, setText] = useState('')
  const [adding, setAdding] = useState(false)
  const [problem, setProblem] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [confirmAll, setConfirmAll] = useState(false)
  const input = useRef(null)

  const load = useCallback(() => {
    setLoadError(null)
    return listMemories().then(
      (list) => setMemories(sortNewestFirst(list)),
      (e) => setLoadError(e.message),
    )
  }, [])

  useEffect(() => {
    let alive = true
    listMemories().then(
      (list) => alive && setMemories(sortNewestFirst(list)),
      (e) => alive && setLoadError(e.message),
    )
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => {
      alive = false
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const full = (memories?.length ?? 0) >= MAX_MEMORIES

  const add = async (e) => {
    e.preventDefault()
    const fact = text.trim()
    if (!fact || adding || full) return
    setAdding(true)
    setProblem(null)
    try {
      const saved = await addMemory(fact)
      setMemories((all) => [saved, ...(all ?? [])])
      setText('')
      input.current?.focus()
    } catch (error) {
      setProblem(error.message)
    } finally {
      setAdding(false)
    }
  }

  const remove = async (id) => {
    setBusyId(id)
    setProblem(null)
    try {
      await deleteMemory(id)
      setMemories((all) => all.filter((m) => m.id !== id))
    } catch (error) {
      if (error.code === 'not_found') setMemories((all) => all.filter((m) => m.id !== id))
      else setProblem(error.message)
    } finally {
      setBusyId(null)
    }
  }

  const removeAll = async () => {
    setBusyId('all')
    setProblem(null)
    try {
      await forgetEverything()
      setMemories([])
      setConfirmAll(false)
    } catch (error) {
      setProblem(error.message)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-labelledby="memory-title" className="dialog-in flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-surface shadow-2xl ring-1 ring-stone-200">
        <header className="flex items-start justify-between gap-3 border-b border-stone-200 px-5 py-4">
          <div>
            <h2 id="memory-title" className="font-display text-xl font-semibold text-ink">
              What I remember about you
            </h2>
            <p className="mt-0.5 text-sm text-stone-600">
              Every conversation uses these as background. I pick them up from long chats, or you add them here.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid size-9 shrink-0 place-items-center rounded-lg text-stone-600 transition hover:bg-stone-100 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand-700"
          >
            <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <form onSubmit={add} className="border-b border-stone-200 px-5 py-4">
          <label htmlFor="memory-input" className="text-xs font-semibold uppercase tracking-wide text-stone-600">
            Add something to remember
          </label>
          <div className="mt-1.5 flex gap-2">
            <input
              id="memory-input"
              ref={input}
              autoFocus
              value={text}
              maxLength={MAX_MEMORY_CHARS}
              disabled={full}
              placeholder={full ? `You have ${MAX_MEMORIES} memories, the most I keep` : 'e.g. I work in the Berlin office'}
              onChange={(e) => {
                setText(e.target.value)
                setProblem(null)
              }}
              className="min-w-0 flex-1 rounded-xl border border-stone-300 bg-surface px-3 py-2.5 text-sm text-ink transition placeholder:text-stone-500 focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-100 disabled:opacity-60"
            />
            <Button type="submit" disabled={!text.trim() || adding || full}>
              {adding ? 'Adding...' : 'Add'}
            </Button>
          </div>
          <p className="mt-1.5 flex justify-between text-xs text-stone-600">
            <span>Short facts only. Passwords and similar are never stored.</span>
            <span aria-live="polite">
              {text.length}/{MAX_MEMORY_CHARS}
            </span>
          </p>
          {problem && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{problem}</p>}
        </form>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {loadError && (
            <div className="p-2">
              <ErrorBanner message={loadError} action={<Button variant="secondary" onClick={load}>Try again</Button>} />
            </div>
          )}
          {!memories && !loadError && <Spinner label="Loading..." className="py-10" />}
          {memories?.length === 0 && (
            <p className="px-2 py-8 text-center text-sm text-stone-600">
              Nothing yet. Add a fact above, or keep chatting: important details from long conversations are remembered.
            </p>
          )}
          <ul>
            {memories?.map((m) => (
              <li key={m.id} className="group flex items-start gap-3 rounded-xl px-2 py-2.5 transition hover:bg-stone-50">
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-highlight" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-wrap break-words text-sm text-ink">{m.text}</p>
                  <p className="mt-0.5 text-xs text-stone-600">
                    {formatDate(m.created_at)} ·{' '}
                    {m.source_conversation_id ? (
                      <button
                        type="button"
                        onClick={() => onOpenConversation(m.source_conversation_id)}
                        className="font-medium text-accent-ink hover:underline focus-visible:outline-2 focus-visible:outline-brand-700"
                      >
                        learned in a chat
                      </button>
                    ) : (
                      'added by you'
                    )}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => remove(m.id)}
                  disabled={busyId !== null}
                  aria-label={`Forget "${m.text}"`}
                  title="Forget this"
                  className="grid size-8 shrink-0 place-items-center rounded-lg text-stone-600 opacity-60 transition hover:bg-red-50 hover:text-red-700 hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-brand-700 disabled:opacity-30 dark:hover:bg-red-950/50 dark:hover:text-red-400"
                >
                  {busyId === m.id ? (
                    <svg className="size-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                  ) : (
                    <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                      <path d="M4 6h12M8 6V4.5h4V6M6 6l.7 9.5h6.6L14 6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {memories?.length > 0 && (
          <footer className="flex items-center justify-between gap-3 border-t border-stone-200 px-5 py-3 text-sm">
            <span className="text-stone-600">
              {memories.length} of {MAX_MEMORIES}
            </span>
            {confirmAll ? (
              <span className="flex items-center gap-2">
                <span className="text-red-800 dark:text-red-300">Forget all {memories.length}?</span>
                <Button variant="danger" className="px-2.5 py-1 text-xs" disabled={busyId === 'all'} onClick={removeAll}>
                  {busyId === 'all' ? 'Forgetting...' : 'Forget everything'}
                </Button>
                <Button variant="secondary" className="px-2.5 py-1 text-xs" disabled={busyId === 'all'} onClick={() => setConfirmAll(false)}>
                  Cancel
                </Button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmAll(true)} className="font-semibold text-red-700 hover:underline dark:text-red-400">
                Forget everything
              </button>
            )}
          </footer>
        )}
      </div>
    </div>
  )
}

function sortNewestFirst(list) {
  return [...list].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
}
