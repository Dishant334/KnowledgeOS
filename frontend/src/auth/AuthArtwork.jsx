// The picture on the sign-in / sign-up panel. It shows what KnowledgeOS does in one image: documents on the left,
// one passage highlighted, and an answer on the right whose [1] points back at it.
// It is drawn in code (no photo, no gradients): pine green, white at low opacity for the paper, and two accents:
// amber ("this is the passage", the highlighter) and teal ("this is the citation").
//
// It is alive but calm (all of it off for people who asked for less motion):
//   * the whole picture floats a few pixels (one slow loop, so the pieces never drift apart),
//   * the three layers shift slightly with the mouse (--mx / --my from hooks/useParallax.js), deeper layers more,
//   * the dashed citation line travels from the passage to the answer, and the two [1] chips pulse now and then.

const AMBER = '#f5b82e'
const TEAL = '#0f6b5c'
const MINT = '#8eccc2'
const PAPER = '#f6f3ec'

// One grey bar standing in for a line of text.
function Line({ x, y, width, tone = 0.2, height = 6 }) {
  return <rect x={x} y={y} width={width} height={height} rx={height / 2} fill="#fff" opacity={tone} />
}

// A layer that shifts with the mouse: `depth` is how many pixels it moves at the edge of the window.
function layer(depth) {
  return {
    transform: `translate(calc(var(--mx, 0) * ${depth}px), calc(var(--my, 0) * ${depth * 0.75}px))`,
    transition: 'transform 300ms ease-out',
  }
}

export default function AuthArtwork({ className = '', slice = false }) {
  return (
    <svg
      viewBox="0 0 480 360"
      className={className}
      preserveAspectRatio={slice ? 'xMidYMid slice' : 'xMidYMid meet'}
      role="img"
      aria-label="A highlighted passage in a document linked to the cited answer it produced"
    >
      <defs>
        <pattern id="auth-grid" width="24" height="24" patternUnits="userSpaceOnUse">
          <path d="M24 0H0V24" fill="none" stroke="#fff" strokeOpacity="0.05" />
        </pattern>
      </defs>
      <rect width="480" height="360" fill="url(#auth-grid)" />

      <g className="art-float-1">
        {/* layer 1: the documents (moves least) */}
        <g style={layer(4)}>
          <g className="auth-rise" style={{ animationDelay: '0ms' }}>
            <rect x="74" y="34" width="210" height="256" rx="14" fill="#fff" fillOpacity="0.04" stroke="#fff" strokeOpacity="0.1" />
            <rect x="54" y="52" width="210" height="256" rx="14" fill="#fff" fillOpacity="0.06" stroke="#fff" strokeOpacity="0.13" />
          </g>

          <g className="auth-rise" style={{ animationDelay: '120ms' }}>
            <rect x="34" y="70" width="210" height="256" rx="14" fill="#fff" fillOpacity="0.1" stroke="#fff" strokeOpacity="0.2" />
            <Line x={54} y={94} width={96} tone={0.55} height={8} />
            <Line x={54} y={124} width={170} />
            <Line x={54} y={140} width={150} />
            <Line x={54} y={156} width={164} />

            {/* the highlighted passage: the highlighter pen */}
            <rect x="46" y="178" width="186" height="46" rx="8" fill={AMBER} fillOpacity="0.22" />
            <rect x="54" y="190" width="168" height="6" rx="3" fill={AMBER} />
            <rect x="54" y="206" width="132" height="6" rx="3" fill={AMBER} />

            <Line x={54} y={244} width={160} />
            <Line x={54} y={260} width={142} />
            <Line x={54} y={276} width={156} />
            <Line x={54} y={292} width={96} />

            {/* [1] badge on the highlighted passage */}
            <g className="art-pulse">
              <rect x="216" y="171" width="32" height="20" rx="10" fill={AMBER} />
              <text x="232" y="185" textAnchor="middle" fontSize="11" fontWeight="700" fill="#422006" fontFamily="ui-sans-serif, system-ui, sans-serif">
                [1]
              </text>
            </g>
          </g>
        </g>

        {/* layer 2: the line from the passage to the citation in the answer */}
        <g style={layer(6)}>
          <g className="auth-rise" style={{ animationDelay: '360ms' }}>
            <path className="art-flow" d="M248 181 C 282 181, 282 265, 316 265" fill="none" stroke={MINT} strokeWidth="1.5" strokeDasharray="4 4" />
            <circle cx="248" cy="181" r="3" fill={MINT} />
          </g>
        </g>

        {/* layer 3: the question and the answer (moves most) */}
        <g style={layer(8)}>
          <g className="auth-rise" style={{ animationDelay: '240ms' }}>
            <rect x="300" y="86" width="150" height="36" rx="18" fill="#40bfaa" fillOpacity="0.3" />
            <Line x={318} y={101} width={104} tone={0.7} />

            <rect x="290" y="146" width="170" height="146" rx="16" fill={PAPER} />
            <rect x="308" y="166" width="22" height="22" rx="11" fill={TEAL} fillOpacity="0.15" />
            <rect x="316" y="174" width="6" height="6" rx="3" fill={TEAL} />
            <rect x="338" y="172" width="70" height="8" rx="4" fill="#a8a290" />
            <rect x="308" y="204" width="134" height="6" rx="3" fill="#d9d3c4" />
            <rect x="308" y="220" width="116" height="6" rx="3" fill="#d9d3c4" />
            <rect x="308" y="236" width="124" height="6" rx="3" fill="#d9d3c4" />
            <g className="art-pulse" style={{ animationDelay: '0.6s' }}>
              <rect x="318" y="254" width="38" height="22" rx="11" fill={TEAL} />
              <text x="337" y="269" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff" fontFamily="ui-sans-serif, system-ui, sans-serif">
                [1]
              </text>
            </g>
          </g>
        </g>
      </g>
    </svg>
  )
}
