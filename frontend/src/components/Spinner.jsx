// A small loading indicator with an optional text. `className` positions it (for example "h-screen" to centre it on the page).
export default function Spinner({ label = '', className = '' }) {
  return (
    <div className={`flex items-center justify-center gap-3 text-stone-600 ${className}`} role="status" aria-live="polite">
      <svg className="h-5 w-5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
      </svg>
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}
