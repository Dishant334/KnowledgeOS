import { useAuth } from '@clerk/clerk-react'
import { motion, useReducedMotion, useScroll, useTransform } from 'motion/react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'

// ── Call to action: "Let's start asking!" in a clearing of tiny shapes that scatter from the cursor ──────────────────────
// A full-screen pine section. Hundreds of small white shapes (dots, squares, triangles, crosses, a few mint and amber) fill
// the edges and leave an organic clearing in the middle for the heading. The cursor pushes the shapes away; each one is
// tied to its home spot by a spring, so they swirl back when the cursor leaves.
//
// How the shapes work (plain 2D canvas, no library):
//  - Positions come from a jittered grid. A shape is kept only OUTSIDE a wobbly ellipse (an ellipse whose radius changes
//    with the angle by a few sine waves), so the clearing looks hand-drawn rather than geometric. The further out, the more
//    the shapes change: dots near the clearing, then squares, triangles and crosses towards the edges.
//  - Every frame: push = (1 − distance / RADIUS)² away from the cursor, spring back to home, damping. Shapes also spin a
//    little when pushed and drift slightly while at rest.
//  - It only animates while the section is on screen. With "reduce motion" the shapes are drawn once and stay still.
//
// The lower half of the field floats on a slow wave. Coming from the white section above, a veil in the page colour fades out
// from the top as the section scrolls in, so the pine floods in rather than starting at a hard edge.
//
// "Continue to scroll" scrolls to whatever comes after this section (the footer today).

const RADIUS = 170 // px: how far the cursor reaches
const PUSH = 4 // how hard it pushes
const SPRING = 0.035 // how strongly a shape returns home
const DAMPING = 0.86

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

function makeShapes(width, height) {
  const random = seeded(7)
  const gap = width < 640 ? 15 : 19
  const cx = width / 2
  const cy = height * 0.47
  const rx = Math.max(170, width * 0.36)
  const ry = Math.max(190, height * 0.36)
  const shapes = []
  for (let y = gap / 2; y < height; y += gap) {
    for (let x = gap / 2; x < width; x += gap) {
      const px = x + (random() - 0.5) * gap * 0.7
      const py = y + (random() - 0.5) * gap * 0.7
      const nx = (px - cx) / rx
      const ny = (py - cy) / ry
      const angle = Math.atan2(ny, nx)
      const wobble = 1 + 0.1 * Math.sin(3 * angle + 1.3) + 0.06 * Math.sin(5 * angle + 0.4) + 0.04 * Math.sin(7 * angle + 2.1)
      const e = Math.hypot(nx, ny) / wobble // below 1 = inside the clearing
      if (e < 1) continue
      if (random() > Math.min(1, (e - 1) / 0.22)) continue // thin at the edge of the clearing, full further out
      if (e > 2.25 && random() < 0.55) continue // and a little lighter far out, so it breathes
      const kind = Math.max(0, Math.min(3, Math.floor((e - 1) / 0.28 + random() * 1.2 - 0.6))) // 0 dot, 1 square, 2 triangle, 3 cross
      const tint = random()
      shapes.push({
        hx: px,
        hy: py,
        x: px,
        y: py,
        vx: 0,
        vy: 0,
        kind,
        size: 6.5 + random() * 3 - (kind === 0 ? 0 : 0.8),
        rot: random() * Math.PI * 2,
        spin: 0,
        phase: random() * Math.PI * 2,
        float: Math.max(0, Math.min(1, (py - height * 0.55) / (height * 0.45))), // 0 above the middle, 1 at the bottom edge
        color: tint < 0.06 ? '#f5b82e' : tint < 0.18 ? '#7fd8c8' : '#ffffff',
      })
    }
  }
  return shapes
}

function draw(ctx, s) {
  ctx.save()
  ctx.translate(s.x, s.y)
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
      for (const s of shapes) {
        if (mouse) {
          const dx = s.x - mouse.x
          const dy = s.y - mouse.y
          const d2 = dx * dx + dy * dy
          if (d2 < RADIUS * RADIUS) {
            const d = Math.sqrt(d2) || 1
            const f = (1 - d / RADIUS) ** 2 * PUSH
            s.vx += (dx / d) * f
            s.vy += (dy / d) * f
            s.spin += f * 0.03 * (s.phase > Math.PI ? 1 : -1)
          }
        }
        // home, plus a slow drift of about a pixel so the field is never completely frozen
        // the lower half floats on a slow wave that rolls from left to right (stronger the lower the shape sits)
        const wave = t * 1.1 - s.hx * 0.012 + s.phase * 0.35
        const homeX = s.hx + Math.sin(t * 0.8 + s.phase) * 1.2 + Math.cos(wave) * 2.5 * s.float
        const homeY = s.hy + Math.cos(t * 0.7 + s.phase) * 1.2 + Math.sin(wave) * 9 * s.float
        s.vx = (s.vx + (homeX - s.x) * SPRING) * DAMPING
        s.vy = (s.vy + (homeY - s.y) * SPRING) * DAMPING
        s.x += s.vx
        s.y += s.vy
        s.rot += s.spin
        s.spin *= 0.94
        draw(ctx, s)
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
      mouse = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    }
    const onLeave = () => {
      mouse = null
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
  const { isLoaded, isSignedIn } = useAuth()

  // scroll to whatever comes next on the page (this section is the last one in <main>, so that is the footer)
  const continueToNext = () => {
    const section = sectionRef.current
    const next = section?.nextElementSibling ?? section?.parentElement?.nextElementSibling
    if (next) next.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
    else window.scrollBy({ top: window.innerHeight, behavior: reduced ? 'auto' : 'smooth' })
  }

  return (
    <section
      id="get-started"
      ref={sectionRef}
      className="relative isolate flex min-h-[100svh] snap-start snap-always flex-col items-center justify-center overflow-hidden bg-[#0f6b5c] px-4 py-32 text-white"
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
        className="absolute bottom-8 left-1/2 z-10 inline-flex h-12 -translate-x-1/2 items-center gap-4 rounded-full bg-white px-6 text-xs font-semibold uppercase tracking-[0.12em] text-[#1a2321] shadow-[0_10px_30px_-10px_rgb(0_0_0/0.35)] transition-colors hover:bg-[#f6f3ec] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
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
