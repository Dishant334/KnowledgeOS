import { useEffect } from 'react'

// Writes the mouse position into two CSS variables on `ref`'s element, --mx and --my, each from -1 (left/top edge of
// the window) to +1 (right/bottom edge). Anything inside can then move a few pixels with the mouse in plain CSS:
//     transform: translate(calc(var(--mx, 0) * 8px), calc(var(--my, 0) * 6px))
// No React state is involved (no re-render per mouse move). It does nothing on touch screens or for people who asked
// their system for less motion.
export default function useParallax(ref) {
  useEffect(() => {
    const element = ref.current
    if (!element) return undefined
    const quiet = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const touch = window.matchMedia('(pointer: coarse)').matches
    if (quiet || touch) return undefined

    let frame = 0
    function onMove(event) {
      cancelAnimationFrame(frame) // at most one update per screen refresh
      frame = requestAnimationFrame(() => {
        element.style.setProperty('--mx', ((event.clientX / window.innerWidth - 0.5) * 2).toFixed(3))
        element.style.setProperty('--my', ((event.clientY / window.innerHeight - 0.5) * 2).toFixed(3))
      })
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      window.removeEventListener('pointermove', onMove)
      cancelAnimationFrame(frame)
    }
  }, [ref])
}
