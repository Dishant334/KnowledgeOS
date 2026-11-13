import { useInView, useReducedMotion } from 'motion/react'
import { useCallback, useEffect, useRef, useState } from 'react'

// ── Demo: a real run of the app, start to finish ──────────────────────────────────────────────────────────────────────
// The video is the project's own screen recording (KnowledgeOS-demo_short.mp4, 30 MB, 1080p), compressed to 2.1 MB: 1280 px
// wide, 24 frames a second, H.264, the black bars cropped off, and "fast start" so it plays before it has fully downloaded.
// It has no sound track, so there is no audio to compress or mute.
//
// It costs the page nothing until someone gets there: `preload="none"` makes the browser fetch only the 43 KB poster
// picture (a frame that shows a cited answer); the video itself is requested when the player comes into view.
//
// It plays by itself when half of the player is on screen, pauses when you scroll away, and carries on from the same second
// when you come back. If you paused it yourself it stays paused (`wantsToPlay`), and with "reduce motion" switched on it
// does not start by itself at all: you press play. The picture is muted (there is no sound anyway), which browsers require
// before they allow a video to start without a click.
//
// The controls are our own (the browser's built-in ones would add a second, clashing set of arrow keys). They sit BELOW the
// picture, because the recording has its own captions burned in along the bottom edge.
//   Buttons: play / pause, −10 s, +10 s, a scrubber, 2x speed, full screen.
//   Keys, working whenever the player is on screen (the video starts by itself, so the player never has to be clicked first;
//   they are ignored while you type in a field):
//        ←  back 10 seconds      →  forward 10 seconds      K  play / pause      F  full screen
//        Space  play / pause, only once the player has the focus (otherwise Space keeps scrolling the page)

const VIDEO = '/demo/knowledgeos-demo.mp4'
const POSTER = '/demo/knowledgeos-demo-poster.jpg'
const DURATION = 113.9 // seconds; used until the browser has read the real length (it reads nothing before play)
const SKIP = 10 // seconds for the −10 / +10 buttons and the arrow keys
const FAST = 2 // the "2x" speed

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

const button = 'inline-flex h-9 items-center justify-center rounded-full px-3 text-sm font-semibold text-ink transition-colors hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-brand-700'

// A round skip button: an arrow circle with "10" inside, like most video players. The arrow ring tilts a little towards its
// direction on hover (not for people who asked for reduced motion) and the whole button presses in when clicked.
function SkipButton({ direction, onClick, disabled }) {
  const forward = direction === 'forward'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={`${forward ? 'Forward' : 'Back'} ${SKIP} seconds`}
      title={`${forward ? 'Forward' : 'Back'} ${SKIP} seconds (${forward ? '→' : '←'})`}
      className="group grid size-10 shrink-0 place-items-center rounded-full border border-stone-200 text-ink transition-colors hover:border-brand-700 hover:bg-brand-100 hover:text-accent-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 disabled:opacity-40 disabled:hover:border-stone-200 disabled:hover:bg-transparent disabled:hover:text-ink motion-safe:active:scale-90"
    >
      <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {/* the ring and its arrow head; the back button is the forward one flipped left to right */}
        <g
          style={{ transformOrigin: '12px 12px' }}
          className={`motion-safe:transition-transform motion-safe:duration-300 ${forward ? 'group-enabled:group-hover:rotate-[28deg]' : 'group-enabled:group-hover:-rotate-[28deg]'}`}
        >
          <g transform={forward ? undefined : 'translate(24 0) scale(-1 1)'}>
            <path d="M12 4a8 8 0 1 1-7.4 5" />
            <path d="M9.6 1.6L12.4 4L9.6 6.4" />
          </g>
        </g>
        <text x="12" y="15.2" textAnchor="middle" fontSize="7.6" fontWeight="700" fill="currentColor" stroke="none" fontFamily="ui-sans-serif, system-ui, sans-serif">
          {SKIP}
        </text>
      </svg>
    </button>
  )
}

export default function Demo() {
  const reduced = useReducedMotion()
  const playerRef = useRef(null)
  const videoRef = useRef(null)
  const wantsToPlay = useRef(true) // false once the visitor has paused it on purpose
  const inView = useInView(playerRef, { amount: 0.5 })
  const [started, setStarted] = useState(false) // the play button in the middle has been pressed once
  const [playing, setPlaying] = useState(false)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(DURATION)
  const [rate, setRate] = useState(1)

  // play by itself when it is on screen, pause when it is not (the position stays where it was)
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    if (inView) {
      if (wantsToPlay.current && !reduced) v.play().catch(() => {}) // refused? then the play button stays for a click
    } else if (!v.paused) {
      v.pause()
    }
  }, [inView, reduced])

  const toggle = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    wantsToPlay.current = v.paused // paused now means: the visitor is starting it; playing now means: stopping it
    if (v.paused) v.play()
    else v.pause()
  }, [])
  const start = () => {
    wantsToPlay.current = true
    setStarted(true)
    videoRef.current?.play()
    playerRef.current?.focus() // so the arrow keys work straight away
  }
  const skip = useCallback((seconds) => {
    const v = videoRef.current
    if (v) v.currentTime = clamp(v.currentTime + seconds, 0, v.duration || DURATION)
  }, [])
  const toggleSpeed = () => {
    const v = videoRef.current
    if (v) v.playbackRate = v.playbackRate === FAST ? 1 : FAST
  }
  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) document.exitFullscreen()
    else playerRef.current?.requestFullscreen?.()
  }, [])

  // the keys, for as long as the player is on screen
  useEffect(() => {
    if (!inView) return
    const onKey = (e) => {
      const v = videoRef.current
      if (!v || v.readyState === 0 || e.altKey || e.ctrlKey || e.metaKey) return // nothing loaded yet: nothing to skip in
      const target = e.target instanceof HTMLElement ? e.target : null
      if (target?.closest('textarea, select, [contenteditable="true"], input:not([type="range"])')) return // typing somewhere else
      const onControl = target?.closest('button, input') // Space on a button already presses it
      const focusedHere = playerRef.current?.contains(document.activeElement)
      if (e.key === 'ArrowLeft') skip(-SKIP)
      else if (e.key === 'ArrowRight') skip(SKIP)
      else if (e.key.toLowerCase() === 'k' || (e.key === ' ' && focusedHere && !onControl)) toggle()
      else if (e.key.toLowerCase() === 'f') toggleFullscreen()
      else return
      e.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [inView, skip, toggle, toggleFullscreen])

  return (
    <section id="demo" className="scroll-mt-28 px-4 py-24 sm:px-6">
      <div className="mx-auto max-w-[1000px]">
        <div className="text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-accent-ink">Demo</p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl lg:text-5xl">See it answer, with sources</h2>
          <p className="mx-auto mt-3 max-w-2xl text-stone-600">A real run from start to finish: your documents, a cited answer, a follow-up question and memory. The captions say which step is running.</p>
        </div>

        <div
          ref={playerRef}
          tabIndex={-1}
          role="group"
          aria-label="Demo video player"
          className="mt-10 rounded-2xl border border-stone-200 bg-surface p-2 shadow-[0_30px_60px_-30px_rgb(15_43_39/0.4)] outline-none focus-visible:ring-2 focus-visible:ring-brand-700 sm:p-3 [&:fullscreen]:flex [&:fullscreen]:flex-col [&:fullscreen]:rounded-none [&:fullscreen]:border-0 [&:fullscreen]:p-4 [&:fullscreen>div:first-child]:aspect-auto [&:fullscreen>div:first-child]:min-h-0 [&:fullscreen>div:first-child]:flex-1 [&:fullscreen_video]:object-contain"
        >
          <div className="relative aspect-[1280/688] overflow-hidden rounded-xl bg-stone-100">
            <video
              ref={videoRef}
              src={VIDEO}
              poster={POSTER}
              preload="none"
              playsInline
              muted
              onClick={started ? toggle : undefined}
              onPlay={() => {
                setPlaying(true)
                setStarted(true)
              }}
              onPause={() => setPlaying(false)}
              onEnded={() => setPlaying(false)}
              onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
              onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
              onRateChange={(e) => setRate(e.currentTarget.playbackRate)}
              aria-label="Screen recording of KnowledgeOS: uploading documents, asking questions, getting cited answers and using memory"
              className="absolute inset-0 size-full cursor-pointer object-cover"
            />
            {!started && (
              <button
                type="button"
                onClick={start}
                aria-label="Play the demo"
                className="group absolute inset-0 grid place-items-center bg-[#0f2b27]/10 transition-colors hover:bg-[#0f2b27]/20 focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-brand-700"
              >
                <span className="grid size-20 place-items-center rounded-full bg-brand-700 text-white shadow-[0_12px_30px_-8px_rgb(15_43_39/0.6)] transition-transform motion-safe:group-hover:scale-110 motion-safe:group-active:scale-95 sm:size-24">
                  <svg viewBox="0 0 24 24" className="ml-1 size-9 sm:size-10" fill="currentColor" aria-hidden="true">
                    <path d="M8 5.5v13a1 1 0 001.5.86l10.5-6.5a1 1 0 000-1.72L9.5 4.64A1 1 0 008 5.5z" />
                  </svg>
                </span>
              </button>
            )}
          </div>

          {/* the controls, under the picture */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-2 px-1 pt-3 sm:flex-nowrap">
            <button type="button" onClick={started ? toggle : start} aria-label={playing ? 'Pause' : 'Play'} title={playing ? 'Pause (Space)' : 'Play (Space)'} className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-700 text-white shadow-[0_6px_14px_-6px_rgb(15_43_39/0.6)] transition hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700 motion-safe:active:scale-95">
              <svg viewBox="0 0 24 24" className="size-5" fill="currentColor" aria-hidden="true">
                {playing ? <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" /> : <path d="M8 5.5v13a1 1 0 001.5.86l10.5-6.5a1 1 0 000-1.72L9.5 4.64A1 1 0 008 5.5z" />}
              </svg>
            </button>
            <SkipButton direction="back" onClick={() => skip(-SKIP)} disabled={!started} />
            <SkipButton direction="forward" onClick={() => skip(SKIP)} disabled={!started} />
            <span className="order-last w-full text-center text-sm tabular-nums text-stone-600 sm:order-none sm:w-auto sm:min-w-[5.5rem] sm:text-left" aria-hidden="true">
              {clock(time)} / {clock(duration)}
            </span>
            <input
              type="range"
              min={0}
              max={duration}
              step={0.1}
              value={Math.min(time, duration)}
              disabled={!started}
              onChange={(e) => {
                if (videoRef.current) videoRef.current.currentTime = Number(e.target.value)
              }}
              aria-label="Seek"
              className="order-last h-2 min-w-0 flex-1 basis-full cursor-pointer accent-brand-700 disabled:cursor-default disabled:opacity-40 sm:order-none sm:basis-0"
            />
            <button
              type="button"
              onClick={toggleSpeed}
              disabled={!started}
              aria-pressed={rate === FAST}
              aria-label="Play at double speed"
              title="Double speed"
              className={`${button} disabled:opacity-40 disabled:hover:bg-transparent ${rate === FAST ? '!bg-brand-700 !text-white hover:!bg-brand-800' : ''}`}
            >
              {FAST}x
            </button>
            <button type="button" onClick={toggleFullscreen} aria-label="Full screen" title="Full screen (F)" className={`${button} w-9 !px-0`}>
              <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
