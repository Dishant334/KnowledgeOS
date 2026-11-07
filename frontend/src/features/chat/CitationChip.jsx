// The small [1] pill inside an answer. Clicking it opens that source in the side panel; the chip of the open source stays filled.
export default function CitationChip({ n, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Open source ${n}`}
      aria-pressed={active}
      className={`mx-0.5 inline-flex min-w-6 items-center justify-center rounded-md px-1.5 text-xs font-semibold align-baseline transition motion-safe:hover:-translate-y-px motion-safe:active:scale-95 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand-700 ${
        active ? 'bg-brand-700 text-white' : 'bg-brand-100 text-brand-800 hover:bg-brand-200'
      }`}
    >
      {n}
    </button>
  )
}
