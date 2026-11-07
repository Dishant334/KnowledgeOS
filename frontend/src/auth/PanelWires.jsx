// Three small "circuit" wires on the dark panel, each with a pulse of light that runs along it, reaches a small node
// (which flares for a moment) and repeats. They sit in the empty corners and along the left edge, away from the text.
//
// How the glow is made without a blur filter (cheap to draw): the same path is stroked four times with the same
// animation: two wide faint strokes (the halo), a medium one, and a thin bright core.
// How the pulse moves: pathLength="100" makes every path 100 units long. A dash pattern of "24 176" (one 24-unit
// dash, then a gap) repeats every 200 units, so only one pulse is ever on the 100-unit path, with a pause between
// pulses. Animating stroke-dashoffset from 24 to -176 (see index.css, @keyframes wire-run) slides the dash along
// the path. With reduced motion the pulses simply stay out of sight and the dim wires remain.

const GREEN = { halo: '#40bfaa', core: '#d8fff3', base: '#8eccc2' }
const AMBER = { halo: '#f5b82e', core: '#fff0c2', base: '#e9c46a' }

// size = the little SVG's box; box edge = where it is anchored on the panel; d = the wire (rounded right-angle bends);
// node = where it ends; seconds/delay = timing of the loop (different on each wire so they never pulse together).
const WIRES = [
  {
    id: 'a', className: 'right-0 top-0', size: [200, 150], palette: GREEN, seconds: 5.2, delay: 0.3,
    d: 'M70 0 V38 Q70 46 78 46 H132 Q140 46 140 54 V104', node: [140, 104],
  },
  {
    id: 'b', className: 'bottom-0 right-0', size: [130, 120], palette: GREEN, seconds: 6.4, delay: 2.1,
    d: 'M130 88 H96 Q88 88 88 80 V52 Q88 44 80 44 H48', node: [48, 44],
  },
  {
    id: 'c', className: 'left-0 top-[170px]', size: [60, 300], palette: AMBER, seconds: 7.2, delay: 1.2,
    d: 'M0 40 H14 Q22 40 22 48 V162 Q22 170 30 170 H32 Q40 170 40 178 V252', node: [40, 252],
  },
]

function Wire({ wire }) {
  const { id, className, size, palette, seconds, delay, d, node } = wire
  const timing = { animationDuration: `${seconds}s`, animationDelay: `${delay}s` }
  const pulse = (width, opacity, color) => (
    <path className="wire-pulse" d={d} pathLength="100" fill="none" stroke={color} strokeWidth={width} strokeOpacity={opacity} strokeLinecap="round" style={timing} />
  )
  return (
    <svg viewBox={`0 0 ${size[0]} ${size[1]}`} width={size[0]} height={size[1]} className={`absolute ${className}`} fill="none" data-wire={id}>
      <path d={d} stroke={palette.base} strokeOpacity="0.22" strokeWidth="1.4" strokeLinecap="round" />
      {pulse(11, 0.14, palette.halo)}
      {pulse(6, 0.28, palette.halo)}
      {pulse(3, 0.55, palette.halo)}
      {pulse(1.8, 1, palette.core)}
      <circle cx={node[0]} cy={node[1]} r="7" fill={palette.halo} fillOpacity="0.18" />
      <circle className="wire-node" cx={node[0]} cy={node[1]} r="2.6" fill={palette.core} style={timing} />
    </svg>
  )
}

export default function PanelWires() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      {WIRES.map((wire) => (
        <Wire key={wire.id} wire={wire} />
      ))}
    </div>
  )
}
