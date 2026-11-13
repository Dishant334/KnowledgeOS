import { motion, useMotionValue, useMotionValueEvent, useReducedMotion, useScroll, useSpring } from 'motion/react'
import { useCallback, useLayoutEffect, useRef, useState } from 'react'

// ── Features: five light playing cards, in three moves as you scroll ───────────────────────────────────────────────────
//   (the deck is already in the middle of the screen when you arrive)
//   1. FAN     it opens into a hand: overlapping cards, each tilted a little more than the last
//   2. TRAVEL  the cards go to their places in the row, the left one first ...
//   3. FLIP    ... and each turns over on the way, ending perfectly straight with its face up
//
// How it works:
//  - The section is much taller than the screen (SECTION_VH) and its content is `sticky`, so it stays on screen while
//    you scroll through the extra height. `useScroll` gives the progress p (0 → 1); `useSpring` smooths it.
//  - Every move is a slice of p turned into its own 0 → 1 number with an easing curve:
//        a = fan (same for all cards), b = travel and f = flip (each card starts a little later than the last)
//  - Then plain maths places the card. Seen from the card's own place in the row, the deck is at (dx, dy) (measured):
//        hand position   hx = dx + fanX × a                 fanX = (i − middle) × FAN_STEP × card width
//                        hy = dy + arc × a                  arc = a shallow curve
//        final position  x = lerp(hx, 0, b)    y = lerp(hy, 0, b) − sin(π·b) × HOP   (the sine is a small hop)
//        tilt            rotation = lerp(fan tilt × a, 0, b)        flip   rotateY = 180° × f
//  - On a short screen the content is shrunk to fit: fit = room ÷ content height (never above 1, never below 0.55).
//  - With "reduce motion" switched on in the system there is no animation: the cards are simply shown face up.

// ── The maths ──
const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))
const lerp = (a, b, t) => a + (b - a) * t // t = 0 gives a, t = 1 gives b, in between a straight line
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2) // slow, quick, slow
const slice = (p, start, end) => clamp((p - start) / (end - start)) // 0 before `start`, 1 after `end`, a straight line between

// ── The numbers to play with (times are shares of the whole scroll) ──
const SECTION_VH = 380 // section height in screen heights
const FAN = [0.04, 0.24] // the deck opens into a hand
const TRAVEL_FIRST = 0.28 // the first card leaves the hand
const TRAVEL_STAGGER = 0.05 // every next card leaves this much later
const TRAVEL_DURATION = 0.26 // how long a card takes to reach its place (it flips during the same time)
const FAN_STEP = 0.5 // distance between neighbouring cards in the hand, in card widths (0.5 = half covered)
const FAN_TILT = 5 // degrees of tilt between neighbouring cards in the hand
const FAN_ARC = 5 // pixels: how much the outer cards of the hand sit lower (a shallow curve)
const HOP = 26 // pixels: the small arch a card makes on its way to its place
const FLOAT_MS = 4200 // one up-and-down float of an open card; must equal `card-float` in index.css
const FLOAT_GAP_MS = 450 // each card floats this much later than the one on its left
// How the deck lies before it opens: a real stack, each card a little off from the one below (fixed, so it looks the
// same every time). [sideways px, up/down px, tilt degrees] per card; the top card is almost straight. It fades out as the fan opens.
const STACK_MESS = [
  [-7, 3, -2.2],
  [5, -2, 1.6],
  [-4, -4, -1.1],
  [6, 2, 2],
  [-1, 0, 0.5],
]

const FEATURES = [
  {
    title: 'Answers with sources',
    text: 'Every answer points to the exact passage it came from. Click it and read the source.',
    icon: <path d="M5 4h14a1 1 0 011 1v11a1 1 0 01-1 1h-9l-4 3v-3H5a1 1 0 01-1-1V5a1 1 0 011-1zM8 9h8M8 12.5h5" />,
  },
  {
    title: 'Reads real files',
    text: 'PDF, Word, PowerPoint, Excel, CSV, Markdown and HTML. Scans are read with OCR.',
    icon: <path d="M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6" />,
  },
  {
    title: 'One chat, its own files',
    text: 'Documents belong to the chat they are added to, so projects never get mixed up.',
    icon: <path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />,
  },
  {
    title: 'Writes as you watch',
    text: 'The answer appears word by word, and you can stop it any time.',
    icon: <path d="M4 7h11M4 12h16M4 17h8" />,
  },
  {
    title: 'Remembers you',
    text: 'Your role and preferences carry across chats. You can see and delete every fact.',
    icon: <path d="M9 4a3 3 0 00-3 3v.3A3 3 0 004 10a3 3 0 001.2 2.4A3 3 0 009 18a2.5 2.5 0 002.5-2.5v-9A2.5 2.5 0 009 4zM15 4a3 3 0 013 3v.3a3 3 0 011.8 2.7 3 3 0 01-1.2 2.4A3 3 0 0115 18a2.5 2.5 0 01-2.5-2.5v-9A2.5 2.5 0 0115 4z" />,
  },
]

export default function Features() {
  const reduced = useReducedMotion()
  const sectionRef = useRef(null)
  const stageRef = useRef(null) // the sticky, screen-high part
  const innerRef = useRef(null) // heading + cards
  const gridRef = useRef(null)
  const cardRefs = useRef([])
  // for each card: how far its place is from the middle of the grid (where the deck lies), in pixels (measured below)
  const [offsets, setOffsets] = useState(() => FEATURES.map(() => ({ dx: 0, dy: 0, w: 0, gridW: 0 })))
  const [fit, setFit] = useState(1) // 1 = full size; less on a short screen

  // progress through the section, 0 to 1, smoothed with a spring
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ['start start', 'end end'] })
  const progress = useSpring(scrollYProgress, { stiffness: 140, damping: 28, mass: 0.4 })

  // Measure where each card's place is in the grid (offsetLeft / offsetTop ignore transforms, so the deck does not disturb
  // it), and how much room the content has on this screen. Again whenever the grid or the window changes size.
  useLayoutEffect(() => {
    const grid = gridRef.current
    const measure = () => {
      const cx = grid.clientWidth / 2
      const cy = grid.clientHeight / 2
      setOffsets(
        cardRefs.current.map((el) => ({
          dx: cx - (el.offsetLeft + el.offsetWidth / 2),
          dy: cy - (el.offsetTop + el.offsetHeight / 2),
          w: el.offsetWidth,
          gridW: grid.clientWidth,
        })),
      )
      if (reduced) {
        setFit(1)
      } else {
        const stage = stageRef.current
        const style = getComputedStyle(stage)
        const room = stage.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom)
        setFit(clamp(room / innerRef.current.offsetHeight, 0.55, 1))
      }
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(grid)
    window.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [reduced])

  return (
    <section id="features" ref={sectionRef} className="relative scroll-mt-28" style={reduced ? undefined : { height: `${SECTION_VH}vh` }}>
      <div
        ref={stageRef}
        className={reduced ? 'px-4 py-24 sm:px-6' : 'sticky top-0 flex h-[100svh] items-center justify-center px-4 pb-6 pt-28 sm:px-6 sm:pt-24'}
      >
        <div ref={innerRef} className="mx-auto w-full max-w-[1480px] origin-center" style={reduced ? undefined : { transform: `scale(${fit})` }}>
          <div className="mb-8 text-center sm:mb-10">
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-ink">Features</p>
            <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl lg:text-5xl">Built so you can check every answer</h2>
            <p className="mx-auto mt-3 hidden max-w-xl text-stone-600 sm:block">Five things KnowledgeOS does, so you never have to take an answer on faith.</p>
          </div>

          {/* the table: each card's own place. The cards start in the middle of it, as a deck. */}
          <div ref={gridRef} className="relative mx-auto grid max-w-[1480px] grid-cols-2 gap-x-3 gap-y-5 sm:grid-cols-3 sm:gap-x-4 sm:gap-y-6 lg:grid-cols-5 lg:gap-x-4">
            {FEATURES.map((feature, i) => (
              <PlayingCard
                key={feature.title}
                feature={feature}
                index={i}
                total={FEATURES.length}
                progress={progress}
                offset={offsets[i]}
                reduced={reduced}
                cardRef={(el) => (cardRefs.current[i] = el)}
              />
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function PlayingCard({ feature, index, total, progress, offset, reduced, cardRef }) {
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const rotate = useMotionValue(0)
  const rotateY = useMotionValue(0)
  const elRef = useRef(null)
  // data-open is "true" once this card has landed and is face up: only then does it start floating. It is written
  // straight onto the element (no React state), because it changes while scrolling.
  const setOpen = useCallback((value) => {
    const el = elRef.current
    if (!el || el.dataset.open === String(value)) return
    // The cards float one after another, like a wave from left to right: every card follows the same shared clock
    // (FLOAT_MS = the card-float duration in index.css), but card i is FLOAT_GAP_MS later than card i - 1.
    if (value) {
      const now = document.timeline.currentTime ?? performance.now()
      const phase = (((now - index * FLOAT_GAP_MS) % FLOAT_MS) + FLOAT_MS) % FLOAT_MS
      el.style.animationDelay = `-${phase}ms`
    }
    el.dataset.open = String(value)
  }, [index])

  // Put the card where the scroll progress `p` says it should be.
  const apply = useCallback(
    (p) => {
      if (reduced) {
        x.set(0), y.set(0), rotate.set(0), rotateY.set(180)
        setOpen(true)
        return
      }
      const k = index - (total - 1) / 2 // position in the hand, counted from its middle (… −1.5, −0.5, 0.5, 1.5 …)
      const travelStart = TRAVEL_FIRST + index * TRAVEL_STAGGER
      const a = easeInOutCubic(slice(p, FAN[0], FAN[1]))
      const b = easeInOutCubic(slice(p, travelStart, travelStart + TRAVEL_DURATION))
      const f = b // the flip runs together with the travel

      // the hand may not be wider than the row of places
      const step = Math.min(FAN_STEP * offset.w, total > 1 ? (offset.gridW - offset.w) / (total - 1) : 0)
      const [mx, my, mr] = STACK_MESS[index % STACK_MESS.length]
      const mess = 1 - a // the stack's messiness is there at the start and gone once the hand is open
      const hx = offset.dx + k * step * a + mx * mess
      const hy = offset.dy + k * k * FAN_ARC * a + my * mess

      x.set(lerp(hx, 0, b))
      y.set(lerp(hy, 0, b) - Math.sin(Math.PI * b) * HOP)
      rotate.set(lerp(k * FAN_TILT * a + mr * mess, 0, b))
      rotateY.set(180 * f)
      setOpen(b >= 1) // completely open: landed and fully turned over
    },
    [index, total, reduced, offset.dx, offset.dy, offset.w, offset.gridW, x, y, rotate, rotateY, setOpen],
  )

  useMotionValueEvent(progress, 'change', apply) // every time the scroll progress changes
  useLayoutEffect(() => apply(progress.get()), [apply, progress]) // and when the measurements change

  const hidden = { backfaceVisibility: 'hidden', WebkitBackfaceVisibility: 'hidden' } // a side hides when it faces away
  const icon = (
    <svg viewBox="0 0 24 24" className="size-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {feature.icon}
    </svg>
  )

  return (
    // The card: 5 wide and 7 tall, like a playing card, and always light, in dark mode too (so the face uses fixed
    // colours, not the theme's). It turns around its vertical middle line; both sides are inside it. In the hand the later cards lie on top.
    <motion.article
      ref={(el) => {
        elRef.current = el
        cardRef(el)
      }}
      style={{ x, y, rotate, rotateY, zIndex: index + 1, transformPerspective: 1200, transformStyle: 'preserve-3d' }}
      // `card-float` (index.css) makes an open card float up and down for ever. It uses CSS `translate`, a separate
      // property from the `transform` the scroll animation writes, so the two never clash.
      className="card-float keep-light relative aspect-[5/7] will-change-transform"
    >
      {/* the back */}
      <div aria-hidden="true" className="absolute inset-0 rounded-[16px] shadow-[0_14px_30px_-14px_rgb(15_43_39/0.35)]" style={hidden}>
        <CardBack />
      </div>

      {/* the face: title and icon at the top, the text, then the title and icon again upside down, as on a playing card */}
      <div
        className="absolute inset-0 flex flex-col rounded-[16px] bg-white p-3.5 text-[#1a2321] ring-1 ring-[#1a2321]/10 shadow-[0_14px_30px_-14px_rgb(15_43_39/0.35)] sm:p-4 lg:p-5"
        style={{ transform: 'rotateY(180deg)', ...hidden }}
      >
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-[13px] font-semibold uppercase leading-[1.25] tracking-wide text-[#1a2321] lg:text-[15px]">{feature.title}</h3>
          <span className="text-[#0f6b5c]">{icon}</span>
        </div>
        <p className="mt-3 border-t border-dashed border-[#1a2321]/20 pt-3 text-[12px] leading-[1.5] text-[#57534e] lg:mt-4 lg:pt-4 lg:text-[14px] lg:leading-[1.55]">{feature.text}</p>
        <div aria-hidden="true" className="mt-auto flex rotate-180 items-start justify-between gap-2">
          <span className="text-[13px] font-semibold uppercase leading-[1.25] tracking-wide text-[#1a2321] lg:text-[15px]">{feature.title}</span>
          <span className="text-[#0f6b5c]">{icon}</span>
        </div>
      </div>
    </motion.article>
  )
}

// The back of every card, light: warm white with fine pine line work. A double frame, a fan in each corner, a tab with
// two rings at the top and bottom, a hatched panel, a diamond, and the KnowledgeOS mark in a ring in the middle.
function CardBack() {
  const line = '#0f6b5c'
  return (
    <svg viewBox="0 0 250 350" className="h-full w-full" aria-hidden="true">
      <defs>
        <pattern id="kos-hatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <path d="M0 0V9" stroke={line} strokeOpacity="0.55" strokeWidth="1" />
        </pattern>
      </defs>
      <rect x="0.75" y="0.75" width="248.5" height="348.5" rx="16" fill="#fbfaf5" stroke={line} strokeOpacity="0.45" strokeWidth="1.5" />
      <g fill="none" stroke={line} strokeWidth="1.4">
        {/* double frame */}
        <rect x="11" y="11" width="228" height="328" rx="9" />
        <rect x="18" y="18" width="214" height="314" rx="5" strokeOpacity="0.6" />
        {/* a fan in each corner */}
        <path d="M18 62A44 44 0 0 0 62 18M18 46A28 28 0 0 0 46 18" />
        <path d="M188 18A44 44 0 0 0 232 62M204 18A28 28 0 0 0 232 46" />
        <path d="M18 288A44 44 0 0 1 62 332M18 304A28 28 0 0 1 46 332" />
        <path d="M232 288A44 44 0 0 0 188 332M232 304A28 28 0 0 0 204 332" />
        {/* the hatched panel */}
        <rect x="62" y="78" width="126" height="194" fill="url(#kos-hatch)" />
        {/* tabs with two rings, top and bottom */}
        <rect x="111" y="18" width="28" height="60" fill="#fbfaf5" />
        <rect x="111" y="272" width="28" height="60" fill="#fbfaf5" />
        <circle cx="125" cy="36" r="6" />
        <circle cx="125" cy="57" r="9" />
        <circle cx="125" cy="314" r="6" />
        <circle cx="125" cy="293" r="9" />
        {/* the diamond and the ring */}
        <path d="M125 96L206 175L125 254L44 175Z" fill="#fbfaf5" />
        <path d="M125 110L192 175L125 240L58 175Z" strokeOpacity="0.6" />
        <circle cx="125" cy="175" r="40" fill="#fbfaf5" />
        <circle cx="125" cy="175" r="33" strokeOpacity="0.6" />
      </g>
      {/* beads down the sides, and amber points on the diamond */}
      <g fill={line}>
        {[112, 128, 144, 206, 222, 238].map((cy) => (
          <g key={cy}>
            <circle cx="40" cy={cy} r="2.2" />
            <circle cx="210" cy={cy} r="2.2" />
          </g>
        ))}
      </g>
      <g fill="#f5b82e">
        <circle cx="125" cy="96" r="3.5" />
        <circle cx="125" cy="254" r="3.5" />
        <circle cx="44" cy="175" r="3.5" />
        <circle cx="206" cy="175" r="3.5" />
      </g>
      {/* the mark: a pine tile with three lines, the middle one amber */}
      <g transform="translate(105 155)">
        <rect width="40" height="40" rx="11" fill="#0f2b27" />
        <rect x="10" y="11" width="20" height="3.6" rx="1.8" fill="#fbfaf5" />
        <rect x="10" y="18.2" width="20" height="4.4" rx="2.2" fill="#f5b82e" />
        <rect x="10" y="26" width="13" height="3.6" rx="1.8" fill="#7fd8c8" />
      </g>
    </svg>
  )
}
