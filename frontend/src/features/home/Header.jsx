import { useAuth } from '@clerk/clerk-react'
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

// ── The home page header, all in this one file ──────────────────────────────────────────────────────────────────────
// A floating frosted-glass bar that stays at the top while the page scrolls. Left: the logo and the page links (the
// current one has a dot). Right: the links that leave the site (with a small arrow), "Sign in" and a dark "Get started"
// pill (or "Open app" when signed in). Below `xl` the links collapse into a menu button. No animation anywhere: hover
// and focus only change colours.
//
// It is `fixed`, so it floats over the first section, which adds its own top space. The side padding keeps the bar clear
// of the dark-mode lamp that hangs in the top-right corner of the page (60 px wide, 24 px from the edge on phones, 48 px
// on desktop): on phones the bar stops before the lamp; from `md` up the bar is inset by the same amount on BOTH sides,
// so it stays centred.

// ── Links ──
const GITHUB_URL = 'https://github.com/Dishant334/KnowledgeOS'

// Left group: the sections of this page. "Home" is the top of the page (`#`); the others are the ids of the sections
// further down. The link whose hash matches the address is the "current" one and gets the dot.
const SECTION_LINKS = [
  { label: 'Home', href: '#' },
  { label: 'Features', href: '#features' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Demo', href: '#demo' },
  { label: 'FAQ', href: '#faq' },
]

// Right group: links that leave the site (they open in a new tab and carry a small arrow).
const EXTERNAL_LINKS = [
  { label: 'GitHub', href: GITHUB_URL },
  { label: 'Docs', href: `${GITHUB_URL}#readme` },
]

// ── Look ──
// FROSTED glass: a faint tint, a strong blur of whatever is behind the bar, a hairline edge and a very soft shadow. The
// tint is `ink` at 6%: ink is dark in light mode and light in dark mode, so one set of classes is a grey veil on a light
// page and a pale veil on a dark one.
const GLASS =
  'bg-ink/[0.06] backdrop-blur-[16px] backdrop-saturate-150 ring-1 ring-ink/[0.07] ' +
  'shadow-[0_1px_2px_rgb(15_43_39/0.04),0_10px_28px_-14px_rgb(15_43_39/0.14)] ' +
  'dark:shadow-[0_10px_28px_-14px_rgb(0_0_0/0.6)]'

// The menu for narrower screens sits over page text, so it is a more solid frosted panel to keep the links readable.
const GLASS_PANEL =
  'bg-surface/80 backdrop-blur-[16px] backdrop-saturate-150 ring-1 ring-ink/[0.08] ' +
  'shadow-[0_10px_28px_-14px_rgb(15_43_39/0.25)] dark:shadow-[0_10px_28px_-14px_rgb(0_0_0/0.7)]'

// A text link in the bar or the menu: quiet by default, a faint veil on hover (an instant change, no transition).
const LINK_CLASS =
  'inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[15px] font-medium text-ink/80 hover:bg-ink/[0.06] hover:text-ink ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700'

// The main call to action: a dark pill (ink on light pages; flips to a pale pill on dark ones).
const PRIMARY =
  'inline-flex items-center justify-center rounded-xl bg-ink px-5 py-2.5 text-[15px] font-medium text-surface hover:opacity-85 ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink'

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false)

  // Esc closes the menu
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e) => e.key === 'Escape' && setMenuOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <header className="fixed inset-x-0 top-0 z-50 pl-3 pr-[5.5rem] pt-3 sm:pl-6 sm:pt-4 md:px-[7.5rem]">
      {/* for keyboard users: the first Tab stop jumps past the header */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-ink focus:ring-2 focus:ring-brand-700"
      >
        Skip to content
      </a>

      <div className="relative mx-auto max-w-[1400px]">
        <nav aria-label="Main" className={`flex items-center gap-2 rounded-[18px] py-2 pl-4 pr-2 ${GLASS}`}>
          <Link to="/" aria-label="KnowledgeOS, home" className="flex shrink-0 items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700">
            <LogoMark />
            <span className="font-display text-lg font-semibold tracking-tight text-accent-ink">KnowledgeOS</span>
          </Link>

          <div className="ml-4 hidden xl:block">
            <SectionLinks />
          </div>

          <div className="ml-auto hidden items-center gap-1 xl:flex">
            <ExternalLinks />
            <span aria-hidden="true" className="mx-1 h-5 w-px bg-ink/15" />
            <AuthLinks />
          </div>

          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            aria-expanded={menuOpen}
            aria-controls="home-mobile-menu"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            className="ml-auto grid size-10 place-items-center rounded-xl text-ink/80 hover:bg-ink/[0.06] hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 xl:hidden"
          >
            <svg viewBox="0 0 20 20" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              {menuOpen ? <path d="M5 5l10 10M15 5L5 15" /> : <path d="M3 6h14M3 10h14M3 14h14" />}
            </svg>
          </button>
        </nav>

        {menuOpen && <MobileMenu id="home-mobile-menu" onClose={() => setMenuOpen(false)} />}
      </div>
    </header>
  )
}

// The page links. The one whose hash matches the address is the current one: darker, with a small dot in front
// (aria-current says the same to screen readers). "Home" (`#`) is current when there is no hash.
// `stacked` = one per row (the menu); `onNavigate` closes that menu.
function SectionLinks({ stacked = false, onNavigate }) {
  const { hash } = useLocation()
  return (
    <ul className={stacked ? 'flex flex-col' : 'flex items-center gap-0.5'}>
      {SECTION_LINKS.map((link) => {
        const current = link.href === '#' ? hash === '' : hash === link.href
        return (
          <li key={link.href}>
            <a
              href={link.href}
              onClick={onNavigate}
              aria-current={current ? 'location' : undefined}
              className={`${LINK_CLASS} ${stacked ? 'w-full py-2.5' : ''} ${current ? 'text-ink' : ''}`}
            >
              {current && <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-ink" />}
              {link.label}
            </a>
          </li>
        )
      })}
    </ul>
  )
}

// The links that leave the site: each opens in a new tab and ends with a small up-right arrow.
function ExternalLinks({ stacked = false }) {
  return (
    <ul className={stacked ? 'flex flex-col' : 'flex items-center gap-0.5'}>
      {EXTERNAL_LINKS.map((link) => (
        <li key={link.href}>
          <a href={link.href} target="_blank" rel="noopener noreferrer" className={`${LINK_CLASS} ${stacked ? 'w-full py-2.5' : ''}`}>
            {link.label}
            <svg viewBox="0 0 10 10" className="size-2.5 opacity-70" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M2.5 7.5l5-5M3 2.5h4.5V7" />
            </svg>
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        </li>
      ))}
    </ul>
  )
}

// Visitors see "Sign in" and "Get started"; once signed in, a single "Open app". Until Clerk has loaded we show the
// visitor buttons (no layout jump). `stacked` = full-width buttons for the menu; `onNavigate` closes that menu.
function AuthLinks({ stacked = false, onNavigate }) {
  const { isLoaded, isSignedIn } = useAuth()
  const wrap = stacked ? 'flex flex-col gap-2' : 'flex items-center gap-1.5'
  const secondary = stacked ? `${LINK_CLASS} justify-center ring-1 ring-ink/15` : LINK_CLASS

  if (isLoaded && isSignedIn) {
    return (
      <div className={wrap}>
        <Link to="/chat" onClick={onNavigate} className={PRIMARY}>
          Open app
        </Link>
      </div>
    )
  }

  return (
    <div className={wrap}>
      <Link to="/sign-in" onClick={onNavigate} className={secondary}>
        Sign in
      </Link>
      <Link to="/sign-up" onClick={onNavigate} className={PRIMARY}>
        Get started
      </Link>
    </div>
  )
}

// The menu for narrower screens: a frosted panel under the bar with the same links and buttons, one per row. It opens
// and closes at once (no animation). Choosing a page link closes it.
function MobileMenu({ id, onClose }) {
  return (
    <div id={id} className={`absolute inset-x-0 top-full mt-2 rounded-[18px] p-3 xl:hidden ${GLASS_PANEL}`}>
      <SectionLinks stacked onNavigate={onClose} />
      <div className="my-2 border-t border-ink/10" />
      <ExternalLinks stacked />
      <div className="mt-3 border-t border-ink/10 pt-3">
        <AuthLinks stacked onNavigate={onClose} />
      </div>
    </div>
  )
}

// The KnowledgeOS mark: a paper tile with three lines, the middle one highlighted in amber.
function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" className="size-8" aria-hidden="true">
      <rect width="32" height="32" rx="9" fill="#0f2b27" />
      <rect x="3" y="3" width="26" height="26" rx="7" fill="#f6f3ec" />
      <rect x="8" y="9" width="16" height="3" rx="1.5" fill="#0f2b27" />
      <rect x="8" y="15" width="16" height="3.5" rx="1.75" fill="#f5b82e" />
      <rect x="8" y="21.5" width="10" height="3" rx="1.5" fill="#0f6b5c" />
    </svg>
  )
}
