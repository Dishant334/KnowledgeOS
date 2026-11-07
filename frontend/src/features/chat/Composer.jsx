import { useRef } from 'react'
import { ACCEPT_ATTRIBUTE } from '../../lib/files'
import { ripple } from '../../lib/ripple'
import UploadChip from '../documents/UploadChip'

// The question box: a rounded card that grows with the text (up to 6 lines) and a round send button.
// The paperclip uploads documents (see features/documents/useUploads.js, owned by ChatLayout so uploads keep going when
// the box moves from the middle to the bottom); each file shows as a chip above the box with its live status.
export default function Composer({ value, onChange, onSubmit, uploads }) {
  const input = useRef(null)
  const field = useRef(null)

  return (
    <div className="mx-auto w-full max-w-[720px] px-4 pb-4">
      {uploads?.items.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2 text-left" aria-label="Files being added">
          {uploads.items.map((item) => (
            <UploadChip key={item.key} item={item} onRemove={uploads.remove} />
          ))}
        </ul>
      )}
      {/* .composer-glow (index.css): a travelling light border and a soft halo while the box has focus */}
      <div className="composer-glow">
        <form
          onMouseDown={(e) => {
            // a click on the box's empty padding focuses the text field (and starts the glow)
            if (e.target === e.currentTarget) {
              e.preventDefault()
              field.current?.focus()
            }
          }}
          onSubmit={(e) => {
            e.preventDefault()
            if (value.trim()) onSubmit(value.trim())
          }}
          className="relative flex items-end gap-2 rounded-2xl bg-surface p-2 shadow-sm ring-1 ring-stone-300 transition focus-within:ring-transparent"
        >
          <input
            ref={input}
            type="file"
            multiple
            accept={ACCEPT_ATTRIBUTE}
            hidden
            onChange={(e) => {
              uploads?.addFiles(e.target.files)
              e.target.value = ''
            }}
          />
          <button
            type="button"
            onClick={() => input.current.click()}
            aria-label="Add documents"
            title="Add documents"
            className="grid size-10 shrink-0 place-items-center rounded-xl text-stone-600 transition hover:bg-stone-100 hover:text-accent-ink focus-visible:outline-2 focus-visible:outline-brand-700 motion-safe:active:scale-95"
          >
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 11.5l-8.6 8.6a5.5 5.5 0 01-7.8-7.8l8.9-8.9a3.7 3.7 0 015.2 5.2l-8.9 8.9a1.8 1.8 0 01-2.6-2.6l8.2-8.2" />
            </svg>
          </button>
          <textarea
            ref={field}
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
      </div>
      <p className="mt-2 text-center text-xs text-stone-600">Answers come only from your uploaded documents.</p>
    </div>
  )
}
