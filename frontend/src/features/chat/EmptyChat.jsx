// CODEBASE-FEATURE (Stage 4): two cards choose the chat's MODE: 'docs' (documents) or 'code' (source code).
// The mode decides which files the paperclip offers and which the backend accepts. It is fixed once the chat has
// started (`locked`): the cards then stay as they are, disabled, and say so. "New chat" starts fresh.
const MODES = [
  {
    id: 'docs',
    title: 'Documents',
    hint: 'PDF, Word, slides, spreadsheets, web pages',
    icon: 'M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6',
  },
  {
    id: 'code',
    title: 'Codebase',
    hint: 'Python, JavaScript, TypeScript, Java, C, C++',
    icon: 'M9 8l-5 4 5 4M15 8l5 4-5 4M13 5l-2 14',
  },
]

const COPY = {
  docs: { heading: 'Ask your documents', help: 'Every answer points to the exact passage it came from, so you can check it yourself.' },
  code: { heading: 'Ask your codebase', help: 'Every answer points to the exact file and lines it came from, so you can check it yourself.' },
}

// A new chat: a heading, one line of help, the two mode cards and the question box in the MIDDLE of the screen. After the first question the box moves to the bottom (see ChatLayout).
export default function EmptyChat({ composer, mode = 'docs', onModeChange, locked = false }) {
  const copy = COPY[mode] ?? COPY.docs
  // no side padding on the wrapper: the question box has its own, so it is not squeezed twice on a phone
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center text-center">
      <h1 className="px-4 font-display text-3xl font-semibold text-ink">{copy.heading}</h1>
      <p className="mt-2 max-w-md px-4 text-stone-600">{copy.help}</p>

      <div role="radiogroup" aria-label="What do you want to ask about?" className="mt-5 grid w-full max-w-md grid-cols-2 gap-3 px-4">
        {MODES.map((m) => {
          const selected = m.id === mode
          return (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={locked}
              onClick={() => onModeChange?.(m.id)}
              className={`flex flex-col items-start gap-1 rounded-xl p-3 text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 motion-safe:enabled:hover:-translate-y-0.5 disabled:cursor-not-allowed ${
                selected ? 'bg-brand-50 ring-2 ring-brand-700' : 'bg-surface ring-1 ring-stone-300 enabled:hover:ring-brand-700 disabled:opacity-50'
              }`}
            >
              <svg viewBox="0 0 24 24" className="size-5 text-accent-ink" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d={m.icon} />
              </svg>
              <span className="text-sm font-semibold text-ink">{m.title}</span>
              <span className="text-xs leading-4 text-stone-600">{m.hint}</span>
            </button>
          )
        })}
      </div>
      {locked && <p className="mt-2 px-4 text-xs text-stone-600">The chat type is fixed once a chat has started. Use New chat to switch.</p>}

      <div className="mt-5 w-full">{composer}</div>
    </div>
  )
}
