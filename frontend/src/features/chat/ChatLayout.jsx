import { useState } from 'react'
import ThemeLamp from '../../components/ThemeLamp'
import DocumentsPanel from '../documents/DocumentsPanel'
import { useUploads } from '../documents/useUploads'
import ChatBackground from './ChatBackground'
import Composer from './Composer'
import CitationPanel from './CitationPanel'
import ConversationSidebar from './ConversationSidebar'
import EmptyChat from './EmptyChat'
import MessageList from './MessageList'
import { SAMPLE_MESSAGES } from './sampleData'

// The chat screen: conversations (left), the chat (middle), and a source panel (right) that exists only while a
// citation is open. Documents are real (upload from the question box, the Documents panel); the chat itself is still
// sample data from sampleData.js until it is connected.
// "/chat" shows the empty new-chat state; "/chat/:id" shows the sample conversation.
export default function ChatLayout({ empty }) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [active, setActive] = useState(null) // { messageId, n } of the open source
  const [draft, setDraft] = useState('')
  const [docsOpen, setDocsOpen] = useState(false)
  const uploads = useUploads() // owned here so uploads survive the box moving from the middle to the bottom

  // The chat's messages live in state. A new chat starts empty; asking adds the question (answers come once the
  // backend is connected). While there are no messages the heading and box sit mid-screen; the first question clears the
  // heading away and the box moves to the bottom.
  const [messages, setMessages] = useState(empty ? [] : SAMPLE_MESSAGES)
  const message = active && messages.find((m) => m.id === active.messageId)
  const citation = message?.citations?.find((c) => c.n === active.n)

  const ask = (text) => {
    const id = Date.now()
    setMessages((all) => [...all, { id, role: 'user', content: text }])
    setDraft('')
  }

  const open = (msg, n) => setActive({ messageId: msg.id, n })

  return (
    <div className="relative flex h-full min-h-0">
      <ConversationSidebar
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeId={null}
        onSelect={() => setDrawerOpen(false)}
        onOpenDocuments={() => {
          setDrawerOpen(false)
          setDocsOpen(true)
        }}
      />

      {/* @container: children can react to the chat area's own width (the lamp needs room when it is narrow) */}
      <section className="@container relative isolate flex min-w-0 flex-1 flex-col">
        <ChatBackground />
        <ThemeLamp className="absolute right-6 top-0 z-20 md:right-10" />
        <div className="flex items-center gap-2 border-b border-stone-200 py-2 pl-3 pr-20 md:hidden">
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
          <EmptyChat composer={<Composer value={draft} onChange={setDraft} onSubmit={ask} uploads={uploads} />} />
        ) : (
          <>
            <MessageList messages={messages} active={active} onOpen={open} />
            <Composer value={draft} onChange={setDraft} onSubmit={ask} uploads={uploads} />
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
      {docsOpen && <DocumentsPanel onClose={() => setDocsOpen(false)} onUpload={uploads.addFiles} uploadsVersion={uploads.version} />}
    </div>
  )
}
