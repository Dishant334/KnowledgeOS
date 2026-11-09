import { Link } from 'react-router-dom'

// Any address the app does not know. Same look as the rest of the app (paper, serif heading, the KnowledgeOS mark)
// and correct in dark mode; one clear way back.
export default function NotFoundPage() {
  return (
    <main className="bg-graph-paper flex min-h-screen flex-col items-center justify-center px-6 text-center">
      <div className="page-in flex max-w-md flex-col items-center">
        <Link to="/chat" aria-label="KnowledgeOS home" className="mb-8 flex items-center gap-2.5">
          <svg viewBox="0 0 32 32" className="size-9" aria-hidden="true">
            <rect width="32" height="32" rx="9" fill="#0f2b27" />
            <rect x="3" y="3" width="26" height="26" rx="7" fill="#f6f3ec" />
            <rect x="8" y="9" width="16" height="3" rx="1.5" fill="#0f2b27" />
            <rect x="8" y="15" width="16" height="3.5" rx="1.75" fill="#f5b82e" />
            <rect x="8" y="21.5" width="10" height="3" rx="1.5" fill="#0f6b5c" />
          </svg>
          <span className="font-display text-xl font-semibold tracking-tight text-accent-ink">KnowledgeOS</span>
        </Link>

        <p className="font-display text-7xl font-semibold leading-none text-stone-300" aria-hidden="true">
          4<span className="text-highlight">0</span>4
        </p>
        <h1 className="mt-4 font-display text-2xl font-semibold text-ink">This page doesn&rsquo;t exist</h1>
        <p className="mt-2 text-stone-600">
          The link may be old or mistyped. Your chats and documents are safe.
        </p>
        <Link
          to="/chat"
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-800 motion-safe:hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
        >
          Back to your chats
          <svg viewBox="0 0 16 16" className="size-4" fill="none" aria-hidden="true">
            <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
      </div>
    </main>
  )
}
