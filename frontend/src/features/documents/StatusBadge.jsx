// The coloured pill for a document's status.
const STYLES = {
  pending: { label: 'Waiting', className: 'bg-stone-100 text-stone-700' },
  processing: { label: 'Processing', className: 'bg-highlight/20 text-amber-800 dark:text-amber-300' },
  ready: { label: 'Ready', className: 'bg-brand-100 text-accent-ink' },
  failed: { label: 'Failed', className: 'bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300' },
}

export default function StatusBadge({ status }) {
  const style = STYLES[status] ?? { label: status, className: 'bg-stone-100 text-stone-700' }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}>
      {status === 'processing' || status === 'pending' ? (
        <span className="size-1.5 animate-pulse rounded-full bg-current" aria-hidden="true" />
      ) : null}
      {style.label}
    </span>
  )
}
