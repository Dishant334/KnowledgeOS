import { useEffect, useRef } from 'react'

// The chat's background: the letters of "KnowledgeOS", spread around the chat but IN READING ORDER: they go left to
// right in a zigzag (high, low, high...), keeping clear of the middle where the heading, messages and box are, and a
// faint dotted line threads through them in order (its dashes slowly travel along it) so the eye reads the word.
// "Knowledge" is filled with a pine gradient and "OS" with an amber one; each letter floats slowly on its own timing.
// MOUSE: a letter near the cursor moves away from it, grows a little and gets stronger, then eases back.
// The values go straight into CSS variables (--tx, --ty, --near) in an animation frame, so React never re-renders.
// Each letter is three nested spans so the motions never fight over one property:
//   outer  = its place (static; measured for the mouse distance)
//   middle = the mouse push (`translate`/`scale`/`opacity`, eased by a CSS transition)
//   inner  = the slow float (`transform` keyframes) and the gradient fill
// Sizes follow the chat's width (container units). Off on touch and for reduced motion.

// x, y in % of the chat area; size relative to the base size; tilt in degrees. Left to right = reading order.
const LETTERS = [
  { c: 'K', x: 8.5, y: 16, size: 1.3, tilt: -8 },
  { c: 'n', x: 13, y: 60, size: 0.95, tilt: 6 },
  { c: 'o', x: 21, y: 28, size: 0.9, tilt: -4 },
  { c: 'w', x: 28, y: 82, size: 1, tilt: 8 },
  { c: 'l', x: 37, y: 10, size: 1.1, tilt: -6 },
  { c: 'e', x: 46, y: 88, size: 0.95, tilt: 5 },
  { c: 'd', x: 55, y: 12, size: 1.05, tilt: -9 },
  { c: 'g', x: 64, y: 84, size: 1, tilt: 6 },
  { c: 'e', x: 73, y: 22, size: 0.9, tilt: -5 },
  { c: 'O', x: 83, y: 68, size: 1.3, tilt: 4, accent: true },
  { c: 'S', x: 92, y: 32, size: 1.25, tilt: -7, accent: true },
]

// a smooth curve through the letters (Catmull-Rom turned into cubic Bezier segments), in the 0..100 coordinate box
function threadPath(points) {
  let d = `M${points[0].x} ${points[0].y}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2] ?? p2
    const c1 = [p1.x + (p2.x - p0.x) / 6, p1.y + (p2.y - p0.y) / 6]
    const c2 = [p2.x - (p3.x - p1.x) / 6, p2.y - (p3.y - p1.y) / 6]
    d += ` C${c1[0].toFixed(2)} ${c1[1].toFixed(2)} ${c2[0].toFixed(2)} ${c2[1].toFixed(2)} ${p2.x} ${p2.y}`
  }
  return d
}
const THREAD = threadPath(LETTERS)

const RADIUS = 220 // px: how far the mouse reaches
const PUSH = 44 // px: the furthest a letter moves away

// `calm` (a conversation is on screen): the whole layer fades to about a third, the thread hides, the letters stop
// floating and stop reacting to the mouse, so long answers are easy to read. The empty chat shows them at full strength.
export default function ChatBackground({ calm = false }) {
  const layer = useRef(null)
  const calmRef = useRef(calm)

  // turning calm on: remember it for the mouse handler and send every letter back to rest
  useEffect(() => {
    calmRef.current = calm
    if (!calm) return
    for (const letter of layer.current?.querySelectorAll('[data-letter]') ?? []) {
      const target = letter.firstElementChild
      target.style.setProperty('--tx', '0px')
      target.style.setProperty('--ty', '0px')
      target.style.setProperty('--near', '0')
    }
  }, [calm])

  useEffect(() => {
    const el = layer.current
    const host = el?.parentElement
    if (!el || !host) return
    if (window.matchMedia('(prefers-reduced-motion: reduce), (pointer: coarse)').matches) return

    const letters = [...el.querySelectorAll('[data-letter]')]
    let mouse = null
    let frame = 0

    const update = () => {
      frame = 0
      for (const letter of letters) {
        const box = letter.getBoundingClientRect() // the outer span never moves with the mouse: no feedback loop
        const dx = box.left + box.width / 2 - (mouse?.x ?? -1e5)
        const dy = box.top + box.height / 2 - (mouse?.y ?? -1e5)
        const distance = Math.hypot(dx, dy) || 1
        const near = Math.max(0, 1 - distance / RADIUS) // 0 far away .. 1 under the cursor
        const push = Math.pow(near, 1.5) * PUSH
        const target = letter.firstElementChild // the middle span owns these variables
        target.style.setProperty('--tx', `${((dx / distance) * push).toFixed(1)}px`)
        target.style.setProperty('--ty', `${((dy / distance) * push).toFixed(1)}px`)
        target.style.setProperty('--near', near.toFixed(3))
      }
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    const onMove = (e) => {
      if (calmRef.current) return // a conversation is on screen: the letters stay still
      mouse = { x: e.clientX, y: e.clientY }
      schedule()
    }
    const onLeave = () => {
      mouse = null
      schedule()
    }

    host.addEventListener('pointermove', onMove)
    host.addEventListener('pointerleave', onLeave)
    return () => {
      host.removeEventListener('pointermove', onMove)
      host.removeEventListener('pointerleave', onLeave)
      cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <div
      ref={layer}
      aria-hidden="true"
      className={`chat-bg pointer-events-none absolute inset-0 -z-10 overflow-hidden select-none ${calm ? 'chat-bg-calm' : ''}`}
      style={{ containerType: 'size' }}
    >
      {/* the thread that links the letters in order (faded out in the middle, behind the heading and box) */}
      <svg
        className="absolute inset-0 h-full w-full"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        fill="none"
        style={{ maskImage: 'radial-gradient(ellipse 34% 26% at 50% 50%, transparent 55%, #000 100%)' }}
      >
        <path
          className="letter-thread"
          d={THREAD}
          stroke="var(--color-brand-600)"
          strokeOpacity="0.18"
          strokeWidth="1.2"
          strokeDasharray="2 7"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      </svg>

      {LETTERS.map((l, i) => (
        <span
          key={i}
          data-letter
          className="absolute inline-block font-display font-semibold leading-none"
          style={{
            left: `${l.x}%`,
            top: `${l.y}%`,
            translate: '-50% -50%',
            rotate: `${l.tilt}deg`,
            fontSize: `calc(clamp(48px, min(11cqw, 16cqh), 150px) * ${l.size})`,
          }}
        >
          <span className="letter-push inline-block">
            <span
              className={`letter-float inline-block ${l.accent ? 'letter-fill-accent' : 'letter-fill'}`}
              style={{ animationDuration: `${7 + (i % 4) * 1.3}s`, animationDelay: `${(-i * 0.9).toFixed(1)}s` }}
            >
              {l.c}
            </span>
          </span>
        </span>
      ))}
    </div>
  )
}
