import { fileTypeLabel } from '../../lib/files'

// One file being added from the question box: its name and what is happening to it right now.
// Plain text only (file names come from the user's disk and are never treated as HTML).
export default function UploadChip({ item, onRemove }) {
  const { status } = item
  const bad = status === 'failed' || status === 'error' || status === 'rejected'

  let line
  if (status === 'uploading') line = `Uploading ${Math.round((item.progress ?? 0) * 100)}%`
  else if (status === 'pending') line = 'Waiting to be processed...'
  else if (status === 'processing') line = 'Reading the document...'
  else if (status === 'ready') line = item.duplicate ? 'Already in your library' : 'Ready to ask about'
  else if (status === 'failed') line = item.failureReason || 'Processing failed.'
  else line = item.error

  return (
    <li
      className={`relative flex w-64 max-w-full items-start gap-2 overflow-hidden rounded-xl bg-surface py-2 pl-2.5 pr-1 text-xs ring-1 ${
        bad ? 'ring-red-300 dark:ring-red-900' : status === 'ready' ? 'ring-brand-300' : 'ring-stone-200'
      }`}
      aria-live="polite"
    >
      <span className="mt-0.5 shrink-0 rounded bg-stone-100 px-1 py-0.5 text-[9px] font-bold text-stone-700">{fileTypeLabel(item.name)}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-ink" title={item.name}>
          {item.name}
        </span>
        <span
          className={`mt-0.5 flex items-center gap-1 ${bad ? 'text-red-700 dark:text-red-400' : status === 'ready' ? 'text-accent-ink' : 'text-stone-600'}`}
        >
          {(status === 'pending' || status === 'processing') && (
            <svg className="size-3 shrink-0 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
          )}
          {status === 'ready' && (
            <svg className="size-3 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
              <path d="M4 10.5l4 4 8-9" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
          <span className="line-clamp-2">{line}</span>
        </span>
      </span>
      <button
        type="button"
        aria-label={`Remove ${item.name} from this list`}
        title={status === 'uploading' ? 'Hide (the upload continues)' : 'Hide'}
        onClick={() => onRemove(item.key)}
        className="grid size-5 shrink-0 place-items-center rounded text-stone-600 hover:bg-stone-100 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand-700"
      >
        <svg viewBox="0 0 20 20" className="size-3" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
          <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
        </svg>
      </button>

      {/* the upload progress bar along the bottom edge */}
      {status === 'uploading' && (
        <span className="absolute inset-x-0 bottom-0 h-0.5 bg-stone-100">
          <span className="block h-full bg-brand-500 transition-[width] duration-200" style={{ width: `${Math.round((item.progress ?? 0) * 100)}%` }} />
        </span>
      )}
    </li>
  )
}
