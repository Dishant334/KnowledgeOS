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
import RenameDialog from './RenameDialog'
import EmptyChat from './EmptyChat'
import MessageList from './MessageList'
import { toCitation } from './citations'
import { useConversations } from './useConversations'

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
  const list = useConversations() // the sidebar
  const [renaming, setRenaming] = useState(null) // the conversation whose name is being edited

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

  // A question asked while a document of this chat is still uploading or being processed would be answered without
  // it (a refusal). Instead it waits, and is sent by itself as soon as every file is ready (or failed); the notice
  // above the box offers "Ask now" and "Cancel".
  const [waiting, setWaiting] = useState(null) // the question text, or null
  const processingNames = uploads.items
    .filter((i) => i.status === 'uploading' || i.status === 'pending' || i.status === 'processing')
    .map((i) => i.name)
  const stillProcessing = processingNames.length > 0

  // Ask a question: the question appears at once, then the answer streams in under it.
  const ask = async (text, { retryOf, force } = {}) => {
    if (streaming.current) return
    if (!force && !retryOf && stillProcessing) {
      setWaiting(text)
      setDraft('')
      return
    }
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
      list.refresh() // a new chat appears in the sidebar; an older one moves to the top
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

  // the sidebar: open another chat (an unused current chat is discarded first), or delete one
  const openConversation = (id) => {
    setDrawerOpen(false)
    if (id === conversation.current.id) return
    discardIfEmpty()
    navigate(`/chat/${id}`)
  }
  const deleteChat = async (id) => {
    await list.remove(id)
    if (id === conversation.current.id) {
      hasMessages.current = true // already deleted: nothing to discard
      newChat()
    }
  }

  // the documents finished: send the waiting question
  useEffect(() => {
    if (waiting === null || stillProcessing || busy) return
    let alive = true
    // started from a microtask, not synchronously inside the effect (it updates state)
    Promise.resolve().then(() => {
      if (!alive) return
      setWaiting(null)
      ask(waiting, { force: true })
    })
    return () => {
      alive = false
    }
    // `ask` is recreated every render; this only needs to react to the documents finishing
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, stillProcessing, busy])

  const waitingNotice = waiting !== null && (
    <WaitingNotice
      question={waiting}
      names={processingNames}
      onAskNow={() => {
        const text = waiting
        setWaiting(null)
        ask(text, { force: true })
      }}
      onCancel={() => {
        setDraft(waiting)
        setWaiting(null)
      }}
    />
  )

  // New chat: a clean screen (no messages, no file chips, empty box). The previous chat is discarded if it was
  // never used (its own files go with it); otherwise it stays in the list with its documents.
  const newChat = () => {
    streaming.current?.abort()
    discardIfEmpty()
    conversation.current = { id: null, pending: null }
    hasMessages.current = false
    setMessages([])
    setLoadState(null)
    setWaiting(null)
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
        activeId={routeId ? Number(routeId) : null}
        onSelect={openConversation}
        onNewChat={newChat}
        conversations={list.conversations}
        error={list.error}
        onRetry={list.refresh}
        onRename={(c) => {
          setDrawerOpen(false)
          setRenaming(c)
        }}
        onDelete={deleteChat}
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
            {list.conversations?.find((c) => c.id === Number(routeId))?.title ?? messages.find((m) => m.role === 'user')?.content ?? 'New chat'}
          </span>
        </div>

        {loadState === 'loading' ? (
          <Spinner label="Opening the conversation..." className="flex-1" />
        ) : loadState?.error ? (
          <div className="mx-auto mt-16 w-full max-w-md px-4">
            <ErrorBanner message={loadState.error} action={<Button variant="secondary" onClick={newChat}>New chat</Button>} />
          </div>
        ) : messages.length === 0 ? (
          <EmptyChat composer={<Composer value={draft} onChange={setDraft} onSubmit={ask} uploads={uploads} busy={busy} onStop={stop} notice={waitingNotice} />} />
        ) : (
          <>
            <MessageList messages={messages} active={active} onOpen={open} onRetry={(m) => ask(m.question, { retryOf: m.id })} />
            <Composer value={draft} onChange={setDraft} onSubmit={ask} uploads={uploads} busy={busy} onStop={stop} notice={waitingNotice} />
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
      {renaming && (
        <RenameDialog
          currentTitle={renaming.title}
          onSave={(title) => list.rename(renaming.id, title)}
          onClose={() => setRenaming(null)}
        />
      )}
    </div>
  )
}

// "Your question will be asked as soon as <file> is ready": shown above the question box while a question waits.
function WaitingNotice({ question, names, onAskNow, onCancel }) {
  const files = names.length === 1 ? `"${names[0]}" is` : `${names.length} documents are`
  return (
    <div role="status" className="page-in mb-2 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-highlight/15 px-3 py-2 text-left text-sm text-ink ring-1 ring-highlight/40">
      <svg className="size-4 shrink-0 animate-spin text-amber-700 dark:text-amber-300" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
      </svg>
      <p className="min-w-0 flex-1">
        {files} still being processed. Your question <span className="font-medium">&ldquo;{question.length > 60 ? `${question.slice(0, 60)}...` : question}&rdquo;</span> will
        be asked as soon as {names.length === 1 ? 'it is' : 'they are'} ready.
      </p>
      <span className="flex shrink-0 gap-2">
        <button type="button" onClick={onAskNow} className="rounded-md px-2 py-0.5 text-xs font-semibold text-accent-ink ring-1 ring-brand-300 transition hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-brand-700">
          Ask now
        </button>
        <button type="button" onClick={onCancel} className="rounded-md px-2 py-0.5 text-xs font-semibold text-stone-700 ring-1 ring-stone-300 transition hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-brand-700">
          Cancel
        </button>
      </span>
    </div>
  )
}
