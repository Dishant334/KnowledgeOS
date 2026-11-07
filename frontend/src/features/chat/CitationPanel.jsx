import { useEffect } from 'react'

// The source panel: file name, page or section and the passage the answer came from (a plain-text quote with an
// amber bar, like a highlighter). Side panel on desktop, bottom sheet on phones. Esc or the X closes it.
export default function CitationPanel({ citation, others, onClose, onSwitch }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <aside
      aria-label={`Source ${citation.n}`}
      className="source-panel fixed inset-x-0 bottom-0 z-30 flex h-[65%] flex-col rounded-t-2xl bg-surface shadow-2xl ring-1 ring-stone-200 md:static md:z-auto md:h-auto md:w-[360px] md:shrink-0 md:rounded-none md:shadow-none md:ring-0 md:border-l md:border-stone-200"
    >
      <div className="flex items-start justify-between gap-3 border-b border-stone-200 p-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-stone-600">Source {citation.n}</p>
          <h2 className="mt-1 truncate font-display text-lg font-semibold text-ink">{citation.filename}</h2>
          <p className="text-sm text-stone-600">
            {citation.page ? `Page ${citation.page}` : citation.section ?? 'Document'}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close source"
          className="grid size-8 shrink-0 place-items-center rounded-lg text-stone-600 transition hover:bg-stone-100 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand-700"
        >
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-600">Passage</p>
        <blockquote className="whitespace-pre-wrap rounded-r-lg border-l-4 border-highlight bg-highlight/15 p-3 text-sm leading-6 text-ink">
          {citation.snippet}
        </blockquote>
      </div>

      {others.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-t border-stone-200 p-4 text-sm text-stone-600">
          Other sources:
          {others.map((c) => (
            <button
              key={c.n}
              type="button"
              onClick={() => onSwitch(c.n)}
              className="rounded-md bg-brand-100 px-2 py-0.5 text-xs font-semibold text-accent-ink transition hover:bg-brand-200 focus-visible:outline-2 focus-visible:outline-brand-700"
            >
              {c.n}
            </button>
          ))}
        </div>
      )}
    </aside>
  )
}
