import AnswerText from './AnswerText'

// One message. The user's question is a soft green bubble on the right; the answer is plain text on the page with its
// source list underneath (each source is a button that opens the same side panel as the chip).
// An answer can also be: being written (status 'streaming': three dots until the first words arrive), 'stopped' (Stop
// pressed: what arrived stays, marked as not saved) or 'error' (a red line with a Retry button).
export default function MessageBubble({ message, activeN, onOpen, onRetry }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-brand-100 px-4 py-2.5 text-ink">
          {message.content}
        </p>
      </div>
    )
  }

  const citations = message.citations ?? []
  return (
    <div>
      <p className="mb-1 font-display text-sm font-semibold text-accent-ink">KnowledgeOS</p>
      {message.status === 'streaming' && !message.content ? (
        <span className="typing-dots inline-flex items-center gap-1 py-2" role="status" aria-label="Writing the answer">
          <span className="size-1.5 rounded-full bg-stone-500" />
          <span className="size-1.5 rounded-full bg-stone-500" />
          <span className="size-1.5 rounded-full bg-stone-500" />
        </span>
      ) : (
        <AnswerText text={message.content} citations={citations} activeN={activeN} onOpen={(n) => onOpen(message, n)} />
      )}
      {message.status === 'stopped' && (
        <p className="mt-1 text-xs text-stone-600">Stopped. This answer was not saved.</p>
      )}
      {message.status === 'error' && (
        <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-red-700 dark:text-red-400" role="alert">
          <span>{message.error}</span>
          {message.question && (
            <button
              type="button"
              onClick={() => onRetry?.(message)}
              className="rounded-md px-2 py-0.5 text-xs font-semibold text-accent-ink ring-1 ring-brand-300 transition hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-brand-700"
            >
              Retry
            </button>
          )}
        </div>
      )}
      {citations.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {citations.map((c) => (
            <li key={c.n}>
              <button
                type="button"
                onClick={() => onOpen(message, c.n)}
                className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-surface px-2.5 py-1 text-xs text-stone-700 ring-1 ring-stone-200 transition hover:ring-brand-400 focus-visible:outline-2 focus-visible:outline-brand-700"
              >
                <span className="rounded bg-brand-100 px-1 font-semibold text-accent-ink">{c.n}</span>
                <span className="truncate">{c.filename}</span>
                {c.shortLocation && <span className="text-stone-600">{c.shortLocation}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
