import { useCallback, useEffect, useMemo, useState } from 'react'
import { ThemeContext } from './ThemeContext'

const KEY = 'kos-theme'

// The first theme: what the user picked last time, otherwise the system setting. Read synchronously, so the first
// paint already has the right colours (no flash). Storage can be unavailable (private mode): then it is not remembered.
function initialTheme() {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* storage blocked */
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

// Light / dark mode for the whole app (sign-in pages included; the Clerk form gets matching colours through
// clerkAppearance.js). The `dark` class goes on this wrapper. The dark colours are CSS variables under `.dark` in
// index.css, so components need no dark: variants for the shared tokens.
export default function ThemeProvider({ children, className = '' }) {
  const [theme, setTheme] = useState(initialTheme)

  useEffect(() => {
    try {
      localStorage.setItem(KEY, theme)
    } catch {
      /* storage blocked */
    }
  }, [theme])

  const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])
  const value = useMemo(() => ({ theme, toggle }), [theme, toggle])

  return (
    <ThemeContext.Provider value={value}>
      <div className={`${theme === 'dark' ? 'dark' : ''} bg-paper text-ink ${className}`}>{children}</div>
    </ThemeContext.Provider>
  )
}
