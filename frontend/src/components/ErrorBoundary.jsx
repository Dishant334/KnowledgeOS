import { Component } from 'react'

// Catches a crash while rendering anywhere below it, so the user sees a friendly page with a way out instead of a
// blank white screen. (React only catches render/lifecycle errors this way; failed requests are handled where they
// happen and show their own messages.) The details go to the browser console, never on screen.
export default class ErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error, info) {
    console.error('KnowledgeOS crashed while rendering:', error, info?.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return <CrashPage />
  }
}

// Stands alone: it cannot rely on the theme provider or the router (either may be what crashed), so it reads the
// saved theme itself and uses plain links.
function CrashPage() {
  let dark = false
  try {
    const saved = localStorage.getItem('kos-theme')
    dark = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    /* storage blocked: light */
  }

  return (
    <div className={`${dark ? 'dark' : ''} h-full`}>
      <main role="alert" className="bg-graph-paper flex min-h-screen flex-col items-center justify-center px-6 text-center">
        <svg viewBox="0 0 32 32" className="mb-6 size-10" aria-hidden="true">
          <rect width="32" height="32" rx="9" fill="#0f2b27" />
          <rect x="3" y="3" width="26" height="26" rx="7" fill="#f6f3ec" />
          <rect x="8" y="9" width="16" height="3" rx="1.5" fill="#0f2b27" />
          <rect x="8" y="15" width="16" height="3.5" rx="1.75" fill="#f5b82e" />
          <rect x="8" y="21.5" width="10" height="3" rx="1.5" fill="#0f6b5c" />
        </svg>
        <h1 className="font-display text-2xl font-semibold text-ink">Something went wrong</h1>
        <p className="mt-2 max-w-sm text-stone-600">
          The page hit an unexpected error. Your chats and documents are safe; reloading usually fixes it.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
          >
            Reload the page
          </button>
          <a
            href="/chat"
            className="rounded-xl bg-surface px-4 py-2.5 text-sm font-medium text-stone-700 ring-1 ring-stone-300 transition hover:bg-stone-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
          >
            Back to your chats
          </a>
        </div>
      </main>
    </div>
  )
}
