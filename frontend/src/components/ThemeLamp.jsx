import { useState } from 'react'
import { useTheme } from '../theme/useTheme'

// The light/dark switch: a small lamp hanging from the top of the chat. Pull its cord (click anywhere on it, or press
// Enter/Space) and it switches: in DARK mode the lamp is on (warm bulb, a soft cone of light falling on the page), in
// LIGHT mode it is off. Each pull stretches the cord and the lamp swings a little. Fixed colours (not the theme
// tokens) so the lamp looks the same object in both modes. With reduced motion: no swing or pull, just the switch.
export default function ThemeLamp({ className = '' }) {
  const { theme, toggle } = useTheme()
  const on = theme === 'dark'
  const [pulls, setPulls] = useState(0) // replays the pull/swing animation; 0 = no animation on first paint

  return (
    <div className={`pointer-events-none ${className}`}>
      {/* the cone of light (only visible when the lamp is on) */}
      <div
        aria-hidden="true"
        className="absolute left-1/2 top-[66px] h-[300px] w-[260px] -translate-x-1/2 transition-opacity duration-700"
        style={{
          opacity: on ? 1 : 0,
          clipPath: 'polygon(44% 0, 56% 0, 100% 100%, 0 100%)',
          background: 'linear-gradient(to bottom, rgb(245 184 46 / 0.16), rgb(245 184 46 / 0.04) 60%, transparent)',
        }}
      />

      <button
        type="button"
        onClick={() => {
          toggle()
          setPulls((n) => n + 1)
        }}
        aria-label={on ? 'Switch to light mode' : 'Switch to dark mode'}
        title={on ? 'Light mode' : 'Dark mode'}
        className="pointer-events-auto relative block cursor-pointer rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
      >
        <span key={pulls} className={`block ${pulls ? 'lamp-swing' : ''}`}>
          <svg viewBox="0 0 60 120" className="h-[120px] w-[60px] overflow-visible" fill="none" aria-hidden="true">
            {/* the wire from the ceiling */}
            <line x1="30" y1="0" x2="30" y2="30" stroke="#8a8a8a" strokeWidth="1.5" />
            <rect x="25.5" y="27" width="9" height="7" rx="2" fill="#4a5553" />

            {/* the bulb's glow (on) */}
            <circle cx="30" cy="61" r="20" fill="url(#lamp-glow)" style={{ opacity: on ? 1 : 0, transition: 'opacity 500ms' }} />

            {/* the shade */}
            <path d="M11 60 C11 44 19 33 30 33 C41 33 49 44 49 60 Z" fill="#2f3a37" />
            <path d="M16 46 C19 39 24 36 30 35.5" stroke="#5b6966" strokeWidth="1.5" strokeLinecap="round" />
            <ellipse cx="30" cy="60" rx="19" ry="3" fill="#1f2725" />

            {/* the bulb */}
            <circle cx="30" cy="62.5" r="5" fill={on ? '#ffe9a8' : '#d6d3d1'} style={{ transition: 'fill 400ms' }} />

            {/* the pull cord and its bead */}
            <g key={`p${pulls}`} className={pulls ? 'lamp-pull' : ''}>
              <line x1="42" y1="58" x2="42" y2="92" stroke="#8a8a8a" strokeWidth="1.2" />
              <circle cx="42" cy="95.5" r="3.6" fill="#c8901a" />
            </g>

            <defs>
              <radialGradient id="lamp-glow">
                <stop offset="0" stopColor="#ffd56b" stopOpacity="0.85" />
                <stop offset="1" stopColor="#ffd56b" stopOpacity="0" />
              </radialGradient>
            </defs>
          </svg>
        </span>
      </button>
    </div>
  )
}
