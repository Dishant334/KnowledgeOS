import { useAuth } from '@clerk/clerk-react'
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from 'motion/react'
import { useRef } from 'react'
import { Link } from 'react-router-dom'

// ── Footer: a full-screen page that is uncovered, not scrolled to ──────────────────────────────────────────────────────
// From tablet width up the footer is `sticky bottom-0` and sits BEHIND <main> (HomePage gives <main> a higher z-index). So it is always pinned
// to the bottom of the screen, hidden under the page, and when the call-to-action above scrolls away it lifts off like a
// sheet (it has rounded bottom corners and a shadow, see Cta.jsx) and uncovers the footer underneath.
//
// While it is being uncovered (`reveal`, 0 → 1 as the page scrolls its last screen):
//   - the footer starts in the CTA's shadow and brightens (a dark veil fades out),
//   - its content rises a little into place and fades in,
//   - the big KnowledgeOS wordmark rises letter by letter, left to right.
// With "reduce motion" everything is simply in place.
//
// On a phone its columns stack and it is taller than the screen, so it is an ordinary footer you scroll through (pinning it
// would hide its top).
//
// The second scroll stop after the CTA is NOT the footer itself: a pinned (sticky) element is always at the screen's edge,
// so as a snap point it caught every small scroll. HomePage puts a 1 px marker at the very end of the page instead.

const GITHUB_URL = 'https://github.com/Dishant334/KnowledgeOS'

const EXPLORE = [
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Proof', href: '#proof' },
  { label: 'Demo', href: '#demo' },
  { label: 'FAQ', href: '#faq' },
]

const PROJECT = [
  { label: 'GitHub', href: GITHUB_URL },
  { label: 'Documentation', href: `${GITHUB_URL}#readme` },
  { label: 'Report an issue', href: `${GITHUB_URL}/issues` },
]

// what the project is built with, and what each part does in it
const STACK = [
  { name: 'FastAPI', role: 'API' },
  { name: 'React', role: 'Interface' },
  { name: 'PostgreSQL', role: 'Files & chats' },
  { name: 'Qdrant', role: 'Vector search' },
  { name: 'Redis', role: 'Queue & limits' },
  { name: 'Celery', role: 'Background work' },
  { name: 'LangChain', role: 'RAG pipeline' },
  { name: 'Qwen3 · Ollama', role: 'Local model' },
]

const WORD = 'KnowledgeOS'

const linkClass =
  'rounded-md text-stone-600 transition-colors hover:text-accent-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700'

function Column({ title, children }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-600">{title}</p>
      <ul className="mt-4 space-y-2.5">{children}</ul>
    </div>
  )
}

// one letter of the wordmark: it rises out of its own line as the footer opens, a little after the letter before it
function Letter({ char, index, reveal, reduced, accent }) {
  const start = 0.35 + index * 0.03
  const y = useTransform(reveal, [start, Math.min(1, start + 0.4)], ['105%', '0%'])
  return (
    <span className="-mb-[0.2em] inline-block overflow-hidden pb-[0.26em] align-bottom">
      <motion.span style={reduced ? undefined : { y }} className={`inline-block ${accent ? 'text-accent-ink' : ''}`}>
        {char}
      </motion.span>
    </span>
  )
}

export default function Footer() {
  const reduced = useReducedMotion()
  const ref = useRef(null)
  const { isLoaded, isSignedIn } = useAuth()

  // 0 when the footer's place starts to come up from the bottom of the screen, 1 when the page has reached its end
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start end', 'end end'] })
  // a soft spring on top, so the footer eases into place instead of following every scroll tick
  const reveal = useSpring(scrollYProgress, { stiffness: 55, damping: 20, mass: 0.6 })
  const shade = useTransform(reveal, [0, 0.85], [0.55, 0])
  const rise = useTransform(reveal, [0, 1], ['12%', '0%'])
  const fade = useTransform(reveal, [0.15, 0.8], [0, 1])

  const toTop = () => window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' })

  return (
    <footer ref={ref} className="relative z-0 flex flex-col overflow-hidden bg-paper text-ink md:sticky md:bottom-0 md:min-h-[100svh]">
      <motion.div
        style={reduced ? undefined : { y: rise, opacity: fade }}
        className="mx-auto flex w-full max-w-[1400px] flex-1 flex-col px-5 pb-6 pt-24 sm:px-10 sm:pt-28 lg:px-16"
      >
        <div className="grid gap-12 lg:grid-cols-[1.3fr_1fr] lg:gap-16">
          {/* left: the promise, and the two ways in */}
          <div>
            <p className="max-w-xl font-display text-4xl font-semibold leading-[1.05] tracking-tight sm:text-5xl">
              Ask your documents.
              <br />
              <span className="text-accent-ink">Check every answer.</span>
            </p>
            <p className="mt-5 max-w-md text-stone-600">
              KnowledgeOS reads your files, answers in plain language, and points every claim to the passage it came from. It runs on
              your own computer.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              {isLoaded && isSignedIn ? (
                <Link to="/chat" className="inline-flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-paper transition-transform motion-safe:hover:-translate-y-0.5">
                  Open app <span aria-hidden="true">→</span>
                </Link>
              ) : (
                <Link to="/sign-up" className="inline-flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-sm font-semibold text-paper transition-transform motion-safe:hover:-translate-y-0.5">
                  Get started <span aria-hidden="true">→</span>
                </Link>
              )}
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-11 items-center gap-2 rounded-full px-5 text-sm font-semibold ring-1 ring-ink/15 transition-colors hover:bg-stone-100"
              >
                Star on GitHub <span aria-hidden="true">↗</span>
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </div>
          </div>

          {/* right: the links */}
          <nav aria-label="Footer" className="grid grid-cols-2 gap-8 sm:grid-cols-3">
            <Column title="Explore">
              {EXPLORE.map((l) => (
                <li key={l.href}>
                  <a href={l.href} className={linkClass}>
                    {l.label}
                  </a>
                </li>
              ))}
            </Column>
            <Column title="Account">
              {isLoaded && isSignedIn ? (
                <li>
                  <Link to="/chat" className={linkClass}>
                    Open app
                  </Link>
                </li>
              ) : (
                <>
                  <li>
                    <Link to="/sign-in" className={linkClass}>
                      Sign in
                    </Link>
                  </li>
                  <li>
                    <Link to="/sign-up" className={linkClass}>
                      Create an account
                    </Link>
                  </li>
                </>
              )}
            </Column>
            <Column title="Project">
              {PROJECT.map((l) => (
                <li key={l.href}>
                  <a href={l.href} target="_blank" rel="noreferrer" className={linkClass}>
                    {l.label} <span aria-hidden="true">↗</span>
                    <span className="sr-only">(opens in a new tab)</span>
                  </a>
                </li>
              ))}
            </Column>
          </nav>
        </div>

        {/* what it is built with: a small spec row, name and job */}
        <div className="mt-12 border-t border-stone-200 pt-6">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-stone-600">Built with</p>
          <ul className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4 lg:grid-cols-8">
            {STACK.map((t) => (
              <li key={t.name} className="border-l border-stone-200 pl-3">
                <p className="text-sm font-semibold text-ink">{t.name}</p>
                <p className="mt-0.5 text-xs text-stone-600">{t.role}</p>
              </li>
            ))}
          </ul>
        </div>

        {/* the big wordmark, pushed to the bottom */}
        <div className="mt-auto pt-10">
          <p
            aria-hidden="true"
            className="select-none whitespace-nowrap font-display font-semibold leading-[0.82] tracking-[-0.04em] text-ink"
            style={{ fontSize: 'clamp(3rem, 12.4vw, 12.5rem)' }} // one line, as wide as the footer
          >
            {WORD.split('').map((char, i) => (
              <Letter key={i} char={char} index={i} reveal={reveal} reduced={reduced} accent={i >= WORD.length - 2} />
            ))}
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-stone-200 pt-5 text-sm text-stone-600">
            <p>© {new Date().getFullYear()} KnowledgeOS · Local-first answers with sources</p>
            <button
              type="button"
              onClick={toTop}
              aria-label="Back to top"
              className="grid size-12 place-items-center rounded-full bg-ink text-paper transition-transform focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 motion-safe:hover:-translate-y-1"
            >
              <svg viewBox="0 0 16 16" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M8 13.5v-11M3.5 7L8 2.5 12.5 7" />
              </svg>
            </button>
          </div>
        </div>
      </motion.div>

      {/* the CTA's shadow on the footer, fading as it lifts away */}
      <motion.div aria-hidden="true" style={reduced ? { opacity: 0 } : { opacity: shade }} className="pointer-events-none absolute inset-0 bg-[#0b1f1c]" />
    </footer>
  )
}
