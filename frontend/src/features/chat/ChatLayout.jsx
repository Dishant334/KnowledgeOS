import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { askStream } from '../../api/askStream'
import {
  createConversation,
  discardConversation,
  discardConversationOnExit,
  getConversation,
  listConversationDocuments,
} from '../../api/conversations'
import Button from '../../components/Button'
import ErrorBanner from '../../components/ErrorBanner'
import Spinner from '../../components/Spinner'
import ThemeLamp from '../../components/ThemeLamp'
import { useUploads } from '../documents/useUploads'
import ChatBackground from './ChatBackground'
import Composer from './Composer'
import CitationPanel from './CitationPanel'
import ConversationSidebar from './ConversationSidebar'
import EmptyChat from './EmptyChat'
import MessageList from './MessageList'
import { toCitation } from './citations'

// The chat screen: conversations (left), the chat (middle), and a source panel (right) that exists only while a
// citation is open. Documents are uploaded with the paperclip (chips above the question box) and belong to this chat;
// questions stream their answer from POST /ask/stream. "/chat" is a new chat; "/chat/:id" opens a saved one.
// After the first answer of a new chat the address becomes /chat/<its id> (the screen is NOT remounted: AppShell keys
// the page by section, so the chat, its chips and any upload in progress stay as they are).
export default function ChatLayout() {
  const { conversationId: routeId } = useParams()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [active, setActive] = useState(null) // { messageId, n } of the open source
  const [draft, setDraft] = useState('')
  const navigate = useNavigate()

  // The backend conversation this screen belongs to. A new chat has none until its first upload or first question:
  // the first of them creates it. One creation at a time: parallel calls share the same promise.
  const conversation = useRef({ id: null, pending: null })
  const getConversationId = useCallback(async () => {
    const current = conversation.current
    if (current.id) return current.id
    if (!current.pending) {
      current.pending = createConversation()
        .then((created) => {
          current.id = created.id
          return created.id
        })
        .finally(() => {
          current.pending = null
        })
    }
    return current.pending
  }, [])

  const uploads = useUploads(getConversationId) // owned here so uploads survive the box moving to the bottom

  // A chat you leave without asking anything is removed with the files uploaded only into it (the backend refuses
  // once it has a message, and sweeps up any it missed after 2 hours). `hasMessages` turns true once the backend has
  // SAVED an answer in it (a stopped or failed question saves nothing).
  const hasMessages = useRef(false)
  const discardIfEmpty = useCallback((onExit = false) => {
    const id = conversation.current.id
    if (!id || hasMessages.current) return
    conversation.current = { id: null, pending: null }
    if (onExit) discardConversationOnExit(id)
    else discardConversation(id).catch(() => {}) // a failure is harmless: the sweep removes it later
  }, [])

  // leaving the page (tab closed, reload) or leaving the chat screen
  useEffect(() => {
    const onPageHide = () => discardIfEmpty(true)
    window.addEventListener('pagehide', onPageHide)
    return () => {
      window.removeEventListener('pagehide', onPageHide)
      discardIfEmpty()
    }
  }, [discardIfEmpty])

  // The messages. A new chat starts empty (heading and box mid-screen); the first question clears the heading away and
  // the box moves to the bottom. An answer being written is { role: 'assistant', status: 'streaming' } and grows token
  // by token; it ends as a normal answer, or 'stopped' (Stop pressed) or 'error' (with a Retry).
  const [messages, setMessages] = useState([])
  const [loadState, setLoadState] = useState(null) // null | 'loading' | { error } while opening a saved chat
  const streaming = useRef(null) // AbortController of the answer being streamed
  const [busy, setBusy] = useState(false)
  const message = active && messages.find((m) => m.id === active.messageId)
  const citation = message?.citations?.find((c) => c.n === active.n)

  const patchMessage = (id, changes) =>
    setMessages((all) => all.map((m) => (m.id === id ? { ...m, ...(typeof changes === 'function' ? changes(m) : changes) } : m)))

  // Opening /chat/:id directly (or from the list, step 3): load its messages and its documents (as chips).
  // Skipped when the address just changed to the chat already on screen (after the first answer of a new chat).
  const { showExisting } = uploads
  useEffect(() => {
    if (!routeId || Number(routeId) === conversation.current.id) return
    let alive = true
    streaming.current?.abort()
    conversation.current = { id: Number(routeId), pending: null }
    hasMessages.current = true // a saved chat is never discarded
    setActive(null)
    setLoadState('loading')
    Promise.all([getConversation(routeId), listConversationDocuments(routeId)]).then(
      ([detail, documents]) => {
        if (!alive) return
        setMessages(
          detail.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, citations: (m.citations ?? []).map(toCitation) })),
        )
        showExisting(documents)
        setLoadState(null)
      },
      (error) => alive && setLoadState({ error: error.code === 'not_found' ? 'This conversation does not exist.' : error.message }),
    )
    return () => {
      alive = false
    }
  }, [routeId, showExisting])

  // Ask a question: the question appears at once, then the answer streams in under it.
  const ask = async (text, { retryOf } = {}) => {
    if (streaming.current) return
    const answerId = `a-${Date.now()}`
    if (retryOf) {
      patchMessage(retryOf, { status: 'streaming', content: '', error: null, citations: [], id: answerId })
    } else {
      setMessages((all) => [
        ...all,
        { id: `q-${Date.now()}`, role: 'user', content: text },
        { id: answerId, role: 'assistant', status: 'streaming', content: '', citations: [], question: text },
      ])
      setDraft('')
    }

    const controller = new AbortController()
    streaming.current = controller
    setBusy(true)
    try {
      const conversationId = await getConversationId()
      const done = await askStream({
        query: text,
        conversationId,
        signal: controller.signal,
        onToken: (piece) => patchMessage(answerId, (m) => ({ content: m.content + piece })),
      })
      // the saved answer replaces the streamed preview (the backend may have tidied it, e.g. a refusal)
      patchMessage(answerId, {
        status: null,
        content: done.answer,
        citations: done.citations.map(toCitation),
        abstained: done.abstained,
      })
      hasMessages.current = true
      if (Number(routeId) !== done.conversation_id) navigate(`/chat/${done.conversation_id}`, { replace: !routeId })
    } catch (error) {
      if (error.name === 'AbortError') {
        patchMessage(answerId, { status: 'stopped' })
      } else {
        const wait = error.retryAfter < 90 ? `${error.retryAfter} seconds` : `${Math.ceil(error.retryAfter / 60)} minutes`
        const reason =
          error.code === 'rate_limited' && error.retryAfter
            ? `Too many questions. Try again in ${wait}.`
            : error.status === 503
              ? 'No AI model is available right now. Please try again in a moment.'
              : error.message
        patchMessage(answerId, { status: 'error', error: reason })
      }
    } finally {
      streaming.current = null
      setBusy(false)
    }
  }

  const stop = () => streaming.current?.abort()

  // New chat: a clean screen (no messages, no file chips, empty box). The previous chat is discarded if it was
  // never used (its own files go with it); otherwise it stays in the list with its documents.
  const newChat = () => {
    streaming.current?.abort()
    discardIfEmpty()
    conversation.current = { id: null, pending: null }
    hasMessages.current = false
    setMessages([])
    setLoadState(null)
    setDraft('')
    setActive(null)
    uploads.reset()
    setDrawerOpen(false)
    navigate('/chat')
  }

  const open = (msg, n) => setActive({ messageId: msg.id, n })

  return (
    <div className="relative flex h-full min-h-0">
      <ConversationSidebar
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeId={null}
        onSelect={() => setDrawerOpen(false)}
        onNewChat={newChat}
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
          <span className="truncate text-sm font-medium text-stone-700">
            {messages.find((m) => m.role === 'user')?.content ?? 'New chat'}
          </span>
        </div>

        {loadState === 'loading' ? (
          <Spinner label="Opening the conversation..." className="flex-1" />
        ) : loadState?.error ? (
          <div className="mx-auto mt-16 w-full max-w-md px-4">
            <ErrorBanner message={loadState.error} action={<Button variant="secondary" onClick={newChat}>New chat</Button>} />
          </div>
        ) : messages.length === 0 ? (
          <EmptyChat composer={<Composer value={draft} onChange={setDraft} onSubmit={ask} uploads={uploads} busy={busy} onStop={stop} />} />
        ) : (
          <>
            <MessageList messages={messages} active={active} onOpen={open} onRetry={(m) => ask(m.question, { retryOf: m.id })} />
            <Composer value={draft} onChange={setDraft} onSubmit={ask} uploads={uploads} busy={busy} onStop={stop} />
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
