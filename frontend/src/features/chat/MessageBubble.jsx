import AnswerText from './AnswerText'

// One message. The user's question is a soft green bubble on the right; the answer is plain text on the page with its
// source list underneath (each source is a button that opens the same side panel as the chip).
export default function MessageBubble({ message, activeN, onOpen }) {
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
      <p className="mb-1 font-display text-sm font-semibold text-brand-800">KnowledgeOS</p>
      <AnswerText text={message.content} citations={citations} activeN={activeN} onOpen={(n) => onOpen(message, n)} />
      {citations.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {citations.map((c) => (
            <li key={c.n}>
              <button
                type="button"
                onClick={() => onOpen(message, c.n)}
                className="inline-flex max-w-full items-center gap-1.5 rounded-lg bg-white px-2.5 py-1 text-xs text-stone-700 ring-1 ring-stone-200 transition hover:ring-brand-400 focus-visible:outline-2 focus-visible:outline-brand-700"
              >
                <span className="rounded bg-brand-100 px-1 font-semibold text-brand-800">{c.n}</span>
                <span className="truncate">{c.filename}</span>
                {c.page && <span className="text-stone-600">p.{c.page}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
