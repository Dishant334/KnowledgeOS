// Runs before every test file (see `test.setupFiles` in vite.config.js).
import '@testing-library/jest-dom/vitest' // extra matchers: toBeInTheDocument(), toBeDisabled(), toHaveValue()...
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Remove whatever the previous test rendered, so every test starts from an empty page.
afterEach(() => {
  cleanup()
  localStorage.clear()
})

// jsdom is a browser made of JavaScript, but it does not have everything a real browser has.
// These stand-ins behave like a desktop browser with default settings (light mode, no reduced motion).
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    onchange: null,
    dispatchEvent: () => false,
  })
}
Element.prototype.scrollTo ??= function scrollTo() {}
Element.prototype.scrollIntoView ??= function scrollIntoView() {}
window.scrollTo = vi.fn()
