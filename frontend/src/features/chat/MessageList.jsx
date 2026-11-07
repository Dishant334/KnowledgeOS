import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble'

const NEAR_BOTTOM_PX = 120

// The scrolling column of messages, centred and at most about 720 px wide so lines stay readable.
// It is the browser's own scroll bar (thin and quiet) with three helpers:
//  - when a message is added it scrolls down to it, unless you had scrolled up to read (then it stays put and the
//    jump button appears), but your own new question always scrolls to the end;
//  - it opens a conversation at the newest message;
//  - a round "jump to latest" button shows while you are scrolled up.
export default function MessageList({ messages, active, onOpen }) {
  const scroller = useRef(null)
  const nearBottom = useRef(true)
  const [showJump, setShowJump] = useState(false)

  const scrollToEnd = (smooth) => {
    const el = scroller.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }

  // the first paint: jump straight to the newest message
  useEffect(() => scrollToEnd(false), [])

  // a message was added
  const last = messages[messages.length - 1]
  useEffect(() => {
    if (nearBottom.current || last?.role === 'user') scrollToEnd(true)
  }, [messages.length, last?.role])

  const onScroll = () => {
    const el = scroller.current
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    nearBottom.current = distance < NEAR_BOTTOM_PX
    setShowJump(distance >= NEAR_BOTTOM_PX)
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scroller}
        onScroll={onScroll}
        className="h-full overflow-y-auto overflow-x-hidden [scrollbar-color:var(--color-stone-300)_transparent] [scrollbar-width:thin]"
      >
        <div className="mx-auto flex w-full max-w-[720px] flex-col gap-6 px-4 py-6 [overflow-wrap:anywhere] @max-[960px]:pr-20">
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              activeN={active?.messageId === m.id ? active.n : null}
              onOpen={onOpen}
            />
          ))}
        </div>
      </div>

      {showJump && (
        <button
          type="button"
          onClick={() => scrollToEnd(true)}
          aria-label="Jump to latest message"
          className="absolute bottom-3 left-1/2 grid size-9 -translate-x-1/2 place-items-center rounded-full bg-surface text-accent-ink shadow-md ring-1 ring-stone-200 transition hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-brand-700 motion-safe:active:scale-95"
        >
          <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M10 4v12M5 11l5 5 5-5" />
          </svg>
        </button>
      )}
    </div>
  )
}
