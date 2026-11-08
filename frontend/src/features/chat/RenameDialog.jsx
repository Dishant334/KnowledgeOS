import { useEffect, useRef, useState } from 'react'
import Button from '../../components/Button'

// A small dialog in the middle of the screen to rename a chat. The current name is filled in and selected, so typing
// replaces it. Enter or Save saves; Esc, Cancel or a click outside closes it. A failed save keeps the dialog open
// with the reason.
export default function RenameDialog({ currentTitle, onSave, onClose }) {
  const [title, setTitle] = useState(currentTitle || '')
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState(null)
  const input = useRef(null)

  useEffect(() => {
    input.current?.focus()
    input.current?.select()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const next = title.trim()
  const unchanged = next === (currentTitle || '').trim()

  const save = async (e) => {
    e.preventDefault()
    if (!next || saving) return
    if (unchanged) return onClose()
    setSaving(true)
    setProblem(null)
    try {
      await onSave(next.slice(0, 255))
      onClose()
    } catch (error) {
      setProblem(error.message)
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <form
        onSubmit={save}
        role="dialog"
        aria-modal="true"
        aria-labelledby="rename-title"
        className="dialog-in w-full max-w-sm rounded-2xl bg-surface p-5 shadow-2xl ring-1 ring-stone-200"
      >
        <h2 id="rename-title" className="font-display text-lg font-semibold text-ink">
          Rename chat
        </h2>
        <label htmlFor="rename-input" className="mt-3 block text-xs font-semibold uppercase tracking-wide text-stone-600">
          Name
        </label>
        <input
          id="rename-input"
          ref={input}
          value={title}
          maxLength={255}
          onChange={(e) => setTitle(e.target.value)}
          className="mt-1.5 w-full rounded-xl border border-stone-300 bg-surface px-3 py-2.5 text-sm text-ink transition focus:border-brand-600 focus:outline-none focus:ring-4 focus:ring-brand-100"
        />
        {problem && <p className="mt-2 text-sm text-red-700 dark:text-red-400">{problem}</p>}
        {!next && <p className="mt-2 text-sm text-stone-600">The name cannot be empty.</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button type="submit" disabled={!next || saving}>
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </div>
      </form>
    </div>
  )
}
