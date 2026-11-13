import { useAuth } from '@clerk/clerk-react'
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'

// ── Call to action: "Let's start asking!" above a floating band of tiny shapes that scatter from the cursor ─────────────
// A full-screen pine section. Small white shapes (dots, squares, triangles, crosses, a few mint and amber) fill ONLY the
// bottom: a band along the bottom edge that rises into the bottom-left and bottom-right corners, like two hills with a dip in
// the middle under the buttons. The top and the upper sides stay clear. The band behaves like water: touching it with the
// cursor splashes the shapes it meets up like droplets (they fall back), and starts ripples that roll out across the band.
//
// How the shapes work (plain 2D canvas, no library):
//  - Positions come from a jittered grid. A shape is kept only BELOW a skyline: high at the left and right edges, low in the
//    middle (a parabola), made uneven by a few sine waves so it looks hand-drawn. The deeper into the band, the more the
//    shapes change: dots along the top of the band, then squares, triangles and crosses towards the bottom.
//  - Ripples start only where the cursor touches the water (in the band or just above it), one every RIPPLE_GAP px of
//    travel, stronger when the cursor moves faster. A ring's front moves out at RIPPLE_SPEED; a shape it has passed moves in
//    a small circle (phase = 2π · distance behind the front / RIPPLE_LENGTH: up and back, down and forward), which is how
//    water really moves under a wave. It fades behind the front, with the ripple's age and as the ring spreads, and the
//    ripples of the last few seconds simply add up. This motion is added where the shape is drawn, so it stays smooth.
//  - Splash: shapes within SPLASH_RADIUS of a moving cursor get an upward kick in proportion to the cursor's speed; a
//    spring pulls them back down, so they arc up and fall like droplets. Shapes drift slightly while at rest.
//  - It only animates while the section is on screen. With "reduce motion" the shapes are drawn once and stay still.
//
// The whole band floats on a slow wave. Coming from the white section above, a veil in the page colour fades out
// from the top as the section scrolls in, so the pine floods in rather than starting at a hard edge.
//
// "Continue to scroll" scrolls to whatever comes after this section (the footer today).

const GLIDE_MS = 1500 // how long the glide from this section to the open footer takes

// the ripples
const RIPPLE_SPEED = 300 // px per second: how fast a ring spreads
const RIPPLE_LENGTH = 170 // px from one crest to the next
const RIPPLE_HEIGHT = 30 // px: how far a shape moves when a fresh, full-strength ripple passes close to where it started
const RIPPLE_LIFE = 3.2 // seconds before a ripple has died out
const RIPPLE_GAP = 55 // px of cursor travel between two new ripples
const MAX_RIPPLES = 12 // the oldest one is dropped beyond this, to keep every frame cheap
const SURFACE_REACH = 70 // px above the band where the cursor already counts as touching the water

// the splash where the cursor touches
const SPLASH_RADIUS = 70 // px
const SPLASH = 0.6 // upward kick per px of cursor movement
const MAX_SPLASH = 16 // px per frame, the biggest kick
const SPRING = 0.03 // how strongly a shape returns to its spot (this is what makes a droplet fall back)
const DAMPING = 0.88 // how much speed is kept each frame

// a small seeded random generator, so the pattern is the same on every visit
function seeded(seed) {
  let a = seed
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// how far down the top of the band is at x (the same curve the shapes are placed under)
function skylineAt(x, width, height) {
  const u = (x - width / 2) / (width / 2) // −1 at the left edge, 0 in the middle, 1 at the right edge
  // 84% down in the middle (below the buttons), rising to 44% at the corners, a little uneven.
  // On a narrow screen the text takes most of the width, so the hills stay low (86% → 70%) and keep clear of it.
  const rise = width < 640 ? 0.16 : 0.4
  const middle = width < 640 ? 0.86 : 0.84
  return height * (middle - rise * u * u + 0.025 * Math.sin(u * 7 + 1.1) + 0.015 * Math.sin(u * 17 + 0.3))
}

function makeShapes(width, height) {
  const random = seeded(7)
  const gap = width < 640 ? 13.7 : 17.3 // 20% more shapes than a 15 / 19 px grid (the spacing shrinks by √1.2)
  const shapes = []
  for (let y = gap / 2; y < height; y += gap) {
    for (let x = gap / 2; x < width; x += gap) {
      const px = x + (random() - 0.5) * gap * 0.7
      const py = y + (random() - 0.5) * gap * 0.7
      const skyline = skylineAt(px, width, height)
      if (py < skyline) continue
      const depth = (py - skyline) / Math.max(1, height - skyline) // 0 at the top of the band, 1 at the bottom edge
      if (random() > Math.min(1, depth / 0.18)) continue // thin along the top of the band, full further down
      const kind = Math.max(0, Math.min(3, Math.floor(depth * 4 + random() * 1.2 - 0.6))) // 0 dot, 1 square, 2 triangle, 3 cross
      const tint = random()
      shapes.push({
        hx: px,
        hy: py,
        x: px,
        y: py,
        vx: 0,
        vy: 0,
        kind,
        size: ((6.5 + random() * 3 - (kind === 0 ? 0 : 0.8)) / 1.4) * 1.5, // 50% bigger than the last size
        rot: random() * Math.PI * 2,
        phase: random() * Math.PI * 2,
        float: 1, // every shape in the band floats
        color: tint < 0.06 ? '#f5b82e' : tint < 0.18 ? '#7fd8c8' : '#ffffff',
      })
    }
  }
  return shapes
}

function draw(ctx, s, offsetX = 0, offsetY = 0) {
  ctx.save()
  ctx.translate(s.x + offsetX, s.y + offsetY)
  ctx.rotate(s.rot)
  ctx.fillStyle = s.color
  ctx.strokeStyle = s.color
  const h = s.size / 2
  if (s.kind === 0) {
    ctx.beginPath()
    ctx.arc(0, 0, h * 0.9, 0, Math.PI * 2)
    ctx.fill()
  } else if (s.kind === 1) {
    ctx.fillRect(-h * 0.85, -h * 0.85, h * 1.7, h * 1.7)
  } else if (s.kind === 2) {
    ctx.beginPath()
    ctx.moveTo(0, -h)
    ctx.lineTo(h, h * 0.8)
    ctx.lineTo(-h, h * 0.8)
    ctx.closePath()
    ctx.fill()
  } else {
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.moveTo(-h, -h)
    ctx.lineTo(h, h)
    ctx.moveTo(h, -h)
    ctx.lineTo(-h, h)
    ctx.stroke()
  }
  ctx.restore()
}

function ShapeField({ reduced }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const section = canvas.parentElement
    const ctx = canvas.getContext('2d')
    let width = 0
    let height = 0
    let shapes = []
    let mouse = null // { x, y } while the cursor is over the section
    let ripples = [] // { x, y, born (seconds), strength }
    let lastRipple = null // where the newest ripple started
    let raf = 0
    let running = false

    const build = () => {
      const rect = section.getBoundingClientRect()
      width = rect.width
      height = rect.height
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      shapes = makeShapes(width, height)
      if (reduced) {
        ctx.clearRect(0, 0, width, height)
        shapes.forEach((s) => draw(ctx, s))
      }
    }

    const frame = (now) => {
      if (!running) return
      raf = requestAnimationFrame(frame)
      const t = now / 1000
      ctx.clearRect(0, 0, width, height)
      ripples = ripples.filter((r) => t - r.born < RIPPLE_LIFE)
      if (mouse) mouse.speed *= 0.8 // a cursor that stops moving stops splashing
      for (const s of shapes) {
        // the splash: a moving cursor kicks the shapes it touches up like droplets
        if (mouse && mouse.speed > 0.5) {
          const dx = s.x - mouse.x
          const dy = s.y - mouse.y
          const d2 = dx * dx + dy * dy
          if (d2 < SPLASH_RADIUS * SPLASH_RADIUS) {
            const d = Math.sqrt(d2) || 1
            const near = (1 - d / SPLASH_RADIUS) ** 2
            s.vy -= Math.min(mouse.speed * SPLASH, MAX_SPLASH) * near
            s.vx += ((dx / d) * 2 + mouse.dx * 0.12) * near
          }
        }
        // home, plus a slow drift of about a pixel so the field is never completely frozen,
        // and the slow wave that rolls through the band from left to right
        const wave = t * 1.1 - s.hx * 0.012 + s.phase * 0.35
        const homeX = s.hx + Math.sin(t * 0.8 + s.phase) * 1.2 + Math.cos(wave) * 2.5 * s.float
        const homeY = s.hy + Math.cos(t * 0.7 + s.phase) * 1.2 + Math.sin(wave) * 9 * s.float
        s.vx = (s.vx + (homeX - s.x) * SPRING) * DAMPING
        s.vy = (s.vy + (homeY - s.y) * SPRING) * DAMPING
        s.x += s.vx
        s.y += s.vy

        // the ripples: every ring that has reached this shape lifts and drops it as it passes
        let bobX = 0
        let bobY = 0
        for (const r of ripples) {
          const age = t - r.born
          const dx = s.hx - r.x
          const dy = s.hy - r.y
          const d = Math.hypot(dx, dy) || 1
          const behind = age * RIPPLE_SPEED - d // how far the front has gone past this shape
          if (behind <= 0) continue // not reached yet
          const strength =
            Math.exp(-behind / (RIPPLE_LENGTH * 1.3)) * // only the first few crests behind the front
            (1 - age / RIPPLE_LIFE) ** 2 * // the ripple dies out
            (1 / (1 + d / 320)) // and weakens as it spreads
          const phase = (2 * Math.PI * behind) / RIPPLE_LENGTH
          const size = RIPPLE_HEIGHT * strength * r.strength
          bobY -= Math.sin(phase) * size // up, then down ...
          bobX += (dx / d) * Math.cos(phase) * size * 0.6 // ... while moving back and forth: a small circle, like water
        }
        const limit = RIPPLE_HEIGHT * 1.6 // several ripples on top of each other never toss a shape too far
        bobY = Math.max(-limit, Math.min(limit, bobY))
        s.rot += bobX * 0.002 // a slight rock as it bobs
        draw(ctx, s, bobX, bobY)
      }
    }

    const start = () => {
      if (running || reduced) return
      running = true
      raf = requestAnimationFrame(frame)
    }
    const stop = () => {
      running = false
      cancelAnimationFrame(raf)
    }

    const onMove = (e) => {
      const rect = section.getBoundingClientRect()
      const x = e.clientX - rect.left
      const y = e.clientY - rect.top
      const moved = mouse ? Math.hypot(x - mouse.x, y - mouse.y) : 0
      mouse = { x, y, dx: mouse ? x - mouse.x : 0, speed: Math.min(60, moved) }
      const touchingWater = y >= skylineAt(x, width, height) - SURFACE_REACH
      if (touchingWater && (!lastRipple || Math.hypot(x - lastRipple.x, y - lastRipple.y) >= RIPPLE_GAP)) {
        lastRipple = { x, y, born: performance.now() / 1000, strength: Math.max(0.4, Math.min(1.3, moved / 16)) }
        ripples.push(lastRipple)
        if (ripples.length > MAX_RIPPLES) ripples.shift()
      }
    }
    const onLeave = () => {
      mouse = null
      lastRipple = null
    }

    build()
    const resize = new ResizeObserver(build)
    resize.observe(section)
    const visibility = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()))
    visibility.observe(section)
    if (!reduced) {
      section.addEventListener('pointermove', onMove)
      section.addEventListener('pointerleave', onLeave)
    }
    return () => {
      stop()
      resize.disconnect()
      visibility.disconnect()
      section.removeEventListener('pointermove', onMove)
      section.removeEventListener('pointerleave', onLeave)
    }
  }, [reduced])

  return <canvas ref={canvasRef} aria-hidden="true" className="pointer-events-none absolute inset-0 size-full" />
}

// A pill button with a dot, like the reference: the dot grows on hover.
function Pill({ to, children, variant }) {
  const look =
    variant === 'light'
      ? 'bg-white text-[#1a2321] hover:bg-[#f6f3ec]'
      : 'bg-[#0f2b27]/70 text-white ring-1 ring-white/25 hover:bg-[#0f2b27]'
  return (
    <Link
      to={to}
      className={`group inline-flex h-12 items-center gap-3 rounded-full px-6 text-sm font-semibold uppercase tracking-[0.08em] transition-[background-color,translate] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white motion-safe:hover:-translate-y-0.5 ${look}`}
    >
      {children}
      <span aria-hidden="true" className={`size-1.5 rounded-full motion-safe:transition-transform motion-safe:duration-300 group-hover:scale-[2.2] ${variant === 'light' ? 'bg-[#0f6b5c]' : 'bg-[#f5b82e]'}`} />
    </Link>
  )
}

export default function Cta() {
  const reduced = useReducedMotion()
  const sectionRef = useRef(null)
  // the hand-over from the section above: while this section's top travels from the bottom of the screen to the top, a
  // veil in the page's own colour (white, or dark in dark mode) fades from its top edge, so the pine seems to flood in
  // instead of starting at a hard line
  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ['start end', 'start start'] })
  const veil = useTransform(scrollYProgress, [0, 0.9], [1, 0])

  // Arriving here, the section fills the screen and the footer stays hidden; one more scroll shows the footer. Done with
  // CSS scroll snapping while the home page is open: this section is a snap point that a scroll cannot skip
  // (`snap-always`), and the footer's end is the next one. "proximity" only snaps near those two points, so the long
  // scroll-driven sections above keep scrolling freely.
  useEffect(() => {
    const root = document.documentElement
    const before = root.style.scrollSnapType
    root.style.scrollSnapType = 'y proximity'
    return () => {
      root.style.scrollSnapType = before
    }
  }, [])

  // The step from this section to the open footer is a slow, eased glide instead of the browser's quick snap: on a screen
  // wide enough for the footer reveal (see Footer.jsx), a scroll down while this section fills the screen glides to the end
  // of the page in GLIDE_MS, and a scroll up from the end glides back. Snapping is paused during the glide so it does not
  // fight it, and extra scrolling during a glide is ignored. "Continue to scroll" uses the same glide.
  const gliding = useRef(false)
  const glideTo = useCallback(
    (target) => {
      if (reduced) {
        window.scrollTo(0, target)
        return
      }
      const root = document.documentElement
      const snap = root.style.scrollSnapType
      root.style.scrollSnapType = 'none'
      const from = window.scrollY
      const start = performance.now()
      const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2) // slow, quicker, slow
      gliding.current = true
      const step = (now) => {
        const t = Math.min(1, (now - start) / GLIDE_MS)
        window.scrollTo(0, from + (target - from) * ease(t))
        if (t < 1) requestAnimationFrame(step)
        else {
          gliding.current = false
          root.style.scrollSnapType = snap
        }
      }
      requestAnimationFrame(step)
    },
    [reduced],
  )
  useEffect(() => {
    const onWheel = (e) => {
      if (gliding.current) {
        e.preventDefault()
        return
      }
      if (window.innerWidth < 768 || !sectionRef.current) return // phones: the footer is not revealed, plain scrolling
      const top = sectionRef.current.getBoundingClientRect().top + window.scrollY
      const end = document.documentElement.scrollHeight - window.innerHeight
      const y = window.scrollY
      if (e.deltaY > 0 && Math.abs(y - top) < 6 && end - top > 40) {
        e.preventDefault()
        glideTo(end)
      } else if (e.deltaY < 0 && y >= end - 6 && end - top > 40) {
        e.preventDefault()
        glideTo(top)
      }
    }
    window.addEventListener('wheel', onWheel, { passive: false })
    return () => window.removeEventListener('wheel', onWheel)
  }, [glideTo])
  const { isLoaded, isSignedIn } = useAuth()

  // scroll to whatever comes next on the page (this section is the last one in <main>, so that is the footer)
  const continueToNext = () => {
    if (gliding.current) return
    glideTo(document.documentElement.scrollHeight - window.innerHeight) // the end of the page: the footer, fully open
  }

  return (
    <section
      id="get-started"
      ref={sectionRef}
      className="relative isolate flex min-h-[100svh] snap-start snap-always flex-col items-center justify-center overflow-hidden rounded-b-[2.5rem] bg-[#0f6b5c] px-4 py-32 text-white shadow-[0_40px_80px_-30px_rgb(11_31_28/0.55)] sm:rounded-b-[4rem]"
    >
      <ShapeField reduced={reduced} />
      {/* a fixed soft edge, so there is never a hard line where the section above ends, even halfway through the fade */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-44 bg-linear-to-b from-surface via-surface/70 to-transparent" />
      <motion.div aria-hidden="true" style={{ opacity: veil }} className="pointer-events-none absolute inset-x-0 top-0 h-[55%] bg-linear-to-b from-surface via-surface/60 to-transparent" />

      {/* small "+" marks across the space, as on the reference */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-[74%] mx-auto flex max-w-[900px] justify-between px-10 text-white/70">
        {[0, 1, 2].map((k) => (
          <svg key={k} viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M8 2v12M2 8h12" />
          </svg>
        ))}
      </div>

      <div className="relative z-10 text-center">
        <p className="text-sm font-semibold uppercase tracking-[0.16em] text-white/85">Ready to stop digging through files?</p>
        <h2 className="mt-5 font-display text-6xl font-semibold leading-[0.95] tracking-tight sm:text-7xl lg:text-8xl">
          Let&apos;s start
          <br />
          asking!
        </h2>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          {isLoaded && isSignedIn ? (
            <Pill to="/chat" variant="light">
              Open app
            </Pill>
          ) : (
            <>
              <Pill to="/sign-up" variant="light">
                Sign up
              </Pill>
              <Pill to="/sign-in" variant="dark">
                Log in
              </Pill>
            </>
          )}
        </div>
      </div>

      {/* continue to scroll: a white pill at the bottom, its arrows bob gently */}
      <button
        type="button"
        onClick={continueToNext}
        className="absolute bottom-8 left-1/2 z-10 inline-flex h-12 -translate-x-1/2 items-center gap-3 whitespace-nowrap rounded-full bg-white px-5 sm:gap-4 sm:px-6 text-xs font-semibold uppercase tracking-[0.12em] text-[#1a2321] shadow-[0_10px_30px_-10px_rgb(0_0_0/0.35)] transition-colors hover:bg-[#f6f3ec] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        <svg viewBox="0 0 16 16" className="cta-bob size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M8 2.5v11M3.5 9L8 13.5 12.5 9" />
        </svg>
        Continue to scroll
        <svg viewBox="0 0 16 16" className="cta-bob size-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M8 2.5v11M3.5 9L8 13.5 12.5 9" />
        </svg>
      </button>
    </section>
  )
}
