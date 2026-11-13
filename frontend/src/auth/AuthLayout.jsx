import { useEffect, useRef, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import useParallax from '../hooks/useParallax'
import { ripple } from '../lib/ripple'
import AuthArtwork from './AuthArtwork'
import ThemeLamp from '../components/ThemeLamp'
import AuthBackdrop from './AuthBackdrop'
import PanelWires from './PanelWires'

// How long the dark panel slides before the form is swapped: just before it lands, when it has fully covered the old
// form. (Swapping earlier would leave both halves empty for a moment.) Keep this a little under the duration-[650ms]
// of the panel below.
const SLIDE_HEAD_START_MS = 600

// What the dark panel says. It always talks about the OTHER page: on /sign-in it invites you to sign up.
const PANEL = {
  'sign-in': {
    title: 'New to KnowledgeOS?',
    text: 'Upload your documents and get answers that cite their sources.',
    button: 'Create an account',
    to: '/sign-up',
    // a glass-outline button, like the reel
    buttonClass: 'border border-white/30 bg-white/10 text-white hover:bg-white/20',
  },
  'sign-up': {
    title: 'Already a member?',
    text: 'Pick up your conversations and documents where you left them.',
    button: 'Sign in',
    to: '/sign-in',
    // a solid paper-coloured button, like the reel's white one
    buttonClass: 'bg-paper text-brand-950 hover:bg-white',
  },
}

function BrandMark() {
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#f6f3ec" />
      <rect x="8" y="9" width="16" height="3" rx="1.5" fill="#0f2b27" />
      <rect x="8" y="15" width="16" height="3.5" rx="1.75" fill="#f5b82e" />
      <rect x="8" y="21.5" width="10" height="3" rx="1.5" fill="#0f6b5c" />
    </svg>
  )
}

function Arrow() {
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1" fill="none" aria-hidden="true">
      <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// The card around the Clerk form. It stays mounted when you go from /sign-in to /sign-up (they are two child
// routes of one layout route), which is what lets the dark panel SLIDE across instead of the page reloading:
//   /sign-in : form on the left,  panel on the right
//   /sign-up : panel on the left, form on the right
// Phones (< 768 px) skip the sliding: the panel becomes a banner on top of the form.
export default function AuthLayout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const routeMode = pathname.startsWith('/sign-up') ? 'sign-up' : 'sign-in' // which form is mounted (follows the URL)
  const signingUpRoute = routeMode === 'sign-up'

  // `pending` is the page the panel is sliding TOWARD. The panel (position and text) follows it at once, while the
  // form stays as it is until SLIDE_HEAD_START_MS later, so the old form is covered by the panel instead of vanishing.
  const [pending, setPending] = useState(null)
  const timer = useRef(null)
  const mode = pending ?? routeMode
  const panel = PANEL[mode]
  const signingUp = mode === 'sign-up'

  // The page element gets --mx / --my (the mouse position) for the artwork and the backdrop.
  const pageRef = useRef(null)
  useParallax(pageRef)

  useEffect(() => () => clearTimeout(timer.current), []) // leaving the page cancels a swap that has not happened yet

  function switchPage() {
    if (pending) return // ignore clicks while a slide is under way
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduceMotion) {
      navigate(panel.to)
      return
    }
    setPending(panel.to === '/sign-up' ? 'sign-up' : 'sign-in')
    timer.current = setTimeout(() => {
      navigate(panel.to)
      setPending(null)
    }, SLIDE_HEAD_START_MS)
  }

  // Clerk draws its own buttons, so one listener on the page gives every Clerk button a click ripple.
  function rippleClerkButtons(event) {
    const button = event.target.closest?.('.cl-rootBox button')
    if (button) ripple(button, event.clientX, event.clientY)
  }

  return (
    <div
      ref={pageRef}
      onPointerDown={rippleClerkButtons}
      className="bg-graph-paper relative isolate flex min-h-screen items-center justify-center overflow-hidden p-4"
    >
      <AuthBackdrop />
      <ThemeLamp className="fixed right-6 top-0 z-30 md:right-12" />

      {/* the wrapper holds the card and the soft glow behind it (the card clips its contents, so the glow is a sibling) */}
      <div className="auth-card-in relative w-full max-w-[1040px]">
        <div aria-hidden="true" className="card-halo pointer-events-none absolute inset-0 rounded-3xl" />
        <div className="relative grid w-full grid-cols-[minmax(0,1fr)] overflow-hidden rounded-3xl bg-surface shadow-xl shadow-brand-950/10 ring-1 ring-brand-300/40 md:min-h-[660px] md:grid-cols-2">
          {/* phone banner (hidden on desktop) */}
          <div className="keep-light relative h-36 overflow-hidden bg-brand-950 md:hidden">
            <AuthArtwork slice className="absolute inset-0 h-full w-full opacity-40" />
            <div className="absolute inset-0 flex items-center gap-3 bg-brand-950/70 px-6">
              <BrandMark />
              <div>
                <p className="font-display text-lg font-semibold text-white">KnowledgeOS</p>
                <p className="text-xs text-brand-200">Ask your documents. Get cited answers.</p>
              </div>
            </div>
          </div>

          {/* the form half: column 1 for sign-in, column 2 for sign-up. key={routeMode} remounts it so it animates in. */}
          <div
            key={routeMode}
            className={`auth-form-in relative z-0 flex min-w-0 items-center justify-center px-6 pb-10 pt-16 sm:px-12 md:pb-6 md:pt-14 ${signingUpRoute ? 'md:col-start-2' : 'md:col-start-1'} md:row-start-1`}
            style={{ '--auth-from': signingUpRoute ? '-28px' : '28px' }}
          >
            {/* the way back to the public home page (top-left of the form half) */}
            <Link
              to="/"
              className="group absolute left-5 top-3 inline-flex items-center gap-1.5 rounded-xl bg-surface px-3 py-1.5 text-sm font-medium text-stone-700 ring-1 ring-stone-300 hover:bg-stone-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 sm:left-8 sm:top-4"
            >
              <svg viewBox="0 0 16 16" className="size-4 motion-safe:transition-transform motion-safe:duration-200 motion-safe:group-hover:-translate-x-0.5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M13 8H3M7 4L3 8l4 4" />
              </svg>
              Back to home
            </Link>
            <div className="w-full max-w-sm">
              <Outlet />
            </div>
          </div>

          {/* the sliding dark panel (desktop only) */}
          <aside
            className={`keep-light absolute inset-y-0 left-0 z-10 hidden w-1/2 flex-col justify-between bg-brand-950 p-10 text-white transition-transform duration-[650ms] ease-[cubic-bezier(0.65,0,0.35,1)] will-change-transform motion-reduce:transition-none md:flex ${signingUp ? 'translate-x-0' : 'translate-x-full'}`}
          >
            <PanelWires />

            <div className="relative flex items-center gap-3">
              <BrandMark />
              <span className="font-display text-xl font-semibold tracking-tight">KnowledgeOS</span>
            </div>

            <AuthArtwork className="relative mx-auto my-4 w-full max-w-[420px]" />

            <div key={mode} className="auth-fade relative space-y-3">
              <h2 className="font-display text-3xl font-semibold tracking-tight">{panel.title}</h2>
              <p className="max-w-xs text-brand-200">{panel.text}</p>
              <button
                type="button"
                onClick={switchPage}
                onPointerDown={(event) => ripple(event.currentTarget, event.clientX, event.clientY)}
                className={`group relative mt-2 inline-flex items-center gap-2 overflow-hidden rounded-xl px-6 py-2.5 text-sm font-semibold backdrop-blur-sm transition duration-200 motion-safe:hover:-translate-y-0.5 motion-safe:active:scale-[0.97] ${panel.buttonClass}`}
              >
                {panel.button}
                <Arrow />
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  )
}
