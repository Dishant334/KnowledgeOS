import { useState } from 'react'
import ChatBackground from './ChatBackground'
import Composer from './Composer'
import CitationPanel from './CitationPanel'
import ConversationSidebar from './ConversationSidebar'
import EmptyChat from './EmptyChat'
import MessageList from './MessageList'
import { SAMPLE_MESSAGES } from './sampleData'

// The chat screen: conversations (left), the chat (middle), and a source panel (right) that exists only while a
// citation is open. UI ONLY for now: everything shown is sample data from sampleData.js.
// "/chat" shows the empty new-chat state; "/chat/:id" shows the sample conversation.
export default function ChatLayout({ empty }) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [active, setActive] = useState(null) // { messageId, n } of the open source
  const [draft, setDraft] = useState('')

  // The chat's messages live in state. A new chat starts empty; asking adds the question (and, until the backend is
  // connected, a stand-in answer). While there are no messages the box sits mid-screen; the first question pushes it down.
  const [messages, setMessages] = useState(empty ? [] : SAMPLE_MESSAGES)
  const message = active && messages.find((m) => m.id === active.messageId)
  const citation = message?.citations?.find((c) => c.n === active.n)

  const ask = (text) => {
    const id = Date.now()
    setMessages((all) => [
      ...all,
      { id, role: 'user', content: text },
      { id: id + 1, role: 'assistant', content: 'Answers will appear here once the chat is connected to your documents.', citations: [] },
    ])
    setDraft('')
  }

  const open = (msg, n) => setActive({ messageId: msg.id, n })

  return (
    <div className="relative flex h-full min-h-0">
      <ConversationSidebar open={drawerOpen} onClose={() => setDrawerOpen(false)} activeId={null} onSelect={() => setDrawerOpen(false)} />

      <section className="relative isolate flex min-w-0 flex-1 flex-col">
        <ChatBackground />
        <div className="flex items-center gap-2 border-b border-stone-200 px-3 py-2 md:hidden">
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open conversations"
            className="grid size-9 place-items-center rounded-lg text-stone-700 hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-brand-700"
          >
            <svg viewBox="0 0 20 20" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M3 5h14M3 10h14M3 15h14" strokeLinecap="round" />
            </svg>
          </button>
          <span className="truncate text-sm font-medium text-stone-700">{empty && messages.length === 0 ? 'New chat' : 'Vacation days and carry-over'}</span>
        </div>

        {messages.length === 0 ? (
          <EmptyChat composer={<Composer value={draft} onChange={setDraft} onSubmit={ask} />} />
        ) : (
          <>
            <MessageList messages={messages} active={active} onOpen={open} />
            <Composer value={draft} onChange={setDraft} onSubmit={ask} />
          </>
        )}
      </section>

      {citation && (
        <CitationPanel
          key={`${active.messageId}-${active.n}`}
          citation={citation}
          others={message.citations.filter((c) => c.n !== citation.n)}
          onClose={() => setActive(null)}
          onSwitch={(n) => setActive({ messageId: active.messageId, n })}
        />
      )}
    </div>
  )
}
