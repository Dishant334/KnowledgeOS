import { useRef, useState } from 'react'
import { ripple } from '../../lib/ripple'

// Types the backend can ingest (documents only: it has no image upload, images exist only as scans inside PDFs).
const ACCEPT = '.pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.html'

// The question box: a white rounded card that grows with the text (up to 6 lines) and a round send button.
// The paperclip picks files to add; they show as removable chips above the box. Looks only for now: nothing is uploaded or sent yet.
export default function Composer({ value, onChange, onSubmit }) {
  const input = useRef(null)
  const [files, setFiles] = useState([])

  return (
    <div className="mx-auto w-full max-w-[720px] px-4 pb-4">
      {files.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="flex max-w-full items-center gap-1.5 rounded-lg bg-white py-1 pl-2.5 pr-1 text-xs text-stone-700 ring-1 ring-stone-200">
              <span className="truncate">{f.name}</span>
              <button
                type="button"
                aria-label={`Remove ${f.name}`}
                onClick={() => setFiles(files.filter((_, j) => j !== i))}
                className="grid size-5 place-items-center rounded text-stone-600 hover:bg-stone-100 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand-700"
              >
                <svg viewBox="0 0 20 20" className="size-3" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" /></svg>
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (value.trim()) onSubmit(value.trim())
        }}
        className="flex items-end gap-2 rounded-2xl bg-white p-2 shadow-sm ring-1 ring-stone-300 transition focus-within:ring-2 focus-within:ring-brand-600"
      >
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            setFiles([...files, ...e.target.files])
            e.target.value = ''
          }}
        />
        <button
          type="button"
          onClick={() => input.current.click()}
          aria-label="Add documents"
          title="Add documents"
          className="grid size-10 shrink-0 place-items-center rounded-xl text-stone-600 transition hover:bg-stone-100 hover:text-brand-800 focus-visible:outline-2 focus-visible:outline-brand-700 motion-safe:active:scale-95"
        >
          <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 11.5l-8.6 8.6a5.5 5.5 0 01-7.8-7.8l8.9-8.9a3.7 3.7 0 015.2 5.2l-8.9 8.9a1.8 1.8 0 01-2.6-2.6l8.2-8.2" />
          </svg>
        </button>
        <textarea
          rows={1}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (value.trim()) onSubmit(value.trim())
            }
          }}
          placeholder="Ask about your documents..."
          aria-label="Your question"
          className="max-h-36 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-ink placeholder:text-stone-500 focus:outline-none [field-sizing:content]"
        />
        <button
          type="submit"
          disabled={!value.trim()}
          aria-label="Send question"
          onPointerDown={(e) => ripple(e.currentTarget, e.clientX, e.clientY)}
          className="relative grid size-10 shrink-0 place-items-center overflow-hidden rounded-xl bg-brand-700 text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-40 motion-safe:enabled:active:scale-95"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="size-5" aria-hidden="true">
            <path d="M10 3.5l6 6-1.4 1.4-3.6-3.6V16.5H9V7.3L5.4 10.9 4 9.5l6-6z" />
          </svg>
        </button>
      </form>
      <p className="mt-2 text-center text-xs text-stone-600">Answers come only from your uploaded documents.</p>
    </div>
  )
}
