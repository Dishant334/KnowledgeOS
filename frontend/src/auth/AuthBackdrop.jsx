// The page behind the sign-in card, on top of the dotted "graph paper": a few faint outlined documents that drift
// very slowly and shift a little AGAINST the mouse (--mx / --my from hooks/useParallax.js), so the page has depth.
// They sit at the edges, away from the card, and are only decoration (hidden from screen readers).
// Two wrappers per document because two things move it: the outer one follows the mouse, the inner one drifts.

const DOCS = [
  { left: '3%', top: '9%', rot: -9, dx: 18, dy: -22, dur: 24, depth: 16, marked: true },
  { left: '83%', top: '6%', rot: 7, dx: -16, dy: 20, dur: 28, depth: 11 },
  { left: '1%', top: '58%', rot: 6, dx: 22, dy: 16, dur: 26, depth: 20 },
  { left: '88%', top: '55%', rot: -7, dx: -20, dy: -18, dur: 22, depth: 13, marked: true },
  { left: '15%', top: '82%', rot: -4, dx: 14, dy: -16, dur: 30, depth: 9, big: true },
  { left: '72%', top: '84%', rot: 10, dx: -14, dy: -20, dur: 25, depth: 17, big: true },
]

function DocSilhouette({ marked }) {
  return (
    <svg viewBox="0 0 120 156" className="h-40 w-[123px] text-ink" fill="none">
      <rect x="1" y="1" width="118" height="154" rx="10" className="fill-surface" fillOpacity="0.55" stroke="currentColor" strokeOpacity="0.14" strokeWidth="1.5" />
      <rect x="16" y="20" width="52" height="6" rx="3" fill="currentColor" fillOpacity="0.16" />
      <rect x="16" y="40" width="88" height="4" rx="2" fill="currentColor" fillOpacity="0.1" />
      <rect x="16" y="52" width="80" height="4" rx="2" fill="currentColor" fillOpacity="0.1" />
      <rect x="16" y="64" width="86" height="4" rx="2" fill="currentColor" fillOpacity="0.1" />
      {marked && <rect x="12" y="78" width="96" height="22" rx="5" fill="#f5b82e" fillOpacity="0.38" />}
      <rect x="16" y="84" width="84" height="4" rx="2" fill="currentColor" fillOpacity={marked ? 0.32 : 0.1} />
      <rect x="16" y="92" width="62" height="4" rx="2" fill="currentColor" fillOpacity={marked ? 0.32 : 0.1} />
      <rect x="16" y="112" width="88" height="4" rx="2" fill="currentColor" fillOpacity="0.1" />
      <rect x="16" y="124" width="70" height="4" rx="2" fill="currentColor" fillOpacity="0.1" />
    </svg>
  )
}

export default function AuthBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {DOCS.map((doc) => (
        <div
          key={`${doc.left}-${doc.top}`}
          className={`absolute ${doc.big ? 'hidden lg:block' : 'hidden sm:block'}`}
          style={{
            left: doc.left,
            top: doc.top,
            transform: `translate(calc(var(--mx, 0) * ${-doc.depth}px), calc(var(--my, 0) * ${-doc.depth * 0.75}px))`,
            transition: 'transform 400ms ease-out',
          }}
        >
          <div
            className="auth-drift"
            style={{ '--r': `${doc.rot}deg`, '--dx': `${doc.dx}px`, '--dy': `${doc.dy}px`, animationDuration: `${doc.dur}s`, transform: `rotate(${doc.rot}deg)` }}
          >
            <DocSilhouette marked={doc.marked} />
          </div>
        </div>
      ))}
    </div>
  )
}
