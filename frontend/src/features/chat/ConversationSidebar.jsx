import { UserButton } from '@clerk/clerk-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { clerkDarkVariables } from '../../auth/clerkAppearance'
import { parseServerDate } from '../../lib/files'
import { useTheme } from '../../theme/useTheme'

// Which day-group a conversation goes in, by the time of its newest message (in the viewer's own time zone).
function groupOf(isoTime, now = new Date()) {
  const date = parseServerDate(isoTime)
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const day = 86400000
  if (date >= startOfToday) return 'Today'
  if (date >= new Date(startOfToday - day)) return 'Yesterday'
  if (date >= new Date(startOfToday - 7 * day)) return 'Previous 7 days'
  if (date >= new Date(startOfToday - 30 * day)) return 'Previous 30 days'
  return 'Older'
}
const GROUP_ORDER = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Older']

// The left column: the name and account menu, New chat, then your conversations grouped by day (newest first).
// Hovering (or focusing) a row shows rename (opens a small dialog, see RenameDialog) and delete (asks first). On phones it is a drawer that slides in over the chat.
export default function ConversationSidebar({
  open,
  onClose,
  activeId,
  onSelect,
  onNewChat,
  conversations,
  error,
  onRetry,
  onRename,
  onDelete,
}) {
  const { theme } = useTheme()
  const grouped = GROUP_ORDER.map((name) => ({
    name,
    rows: (conversations ?? []).filter((c) => groupOf(c.last_message_at) === name),
  })).filter((g) => g.rows.length)

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={onClose} aria-hidden="true" />}
      <nav
        aria-label="Conversations"
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-stone-200 bg-stone-50 transition-transform duration-300 md:static md:z-auto md:w-72 md:shrink-0 md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
          <Link to="/chat" onClick={onNewChat} className="font-display text-xl font-semibold tracking-tight text-accent-ink">
            KnowledgeOS
          </Link>
          <UserButton appearance={theme === 'dark' ? { variables: clerkDarkVariables } : undefined} />
        </div>

        <div className="p-3">
          <button
            type="button"
            onClick={onNewChat}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-700 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-800 motion-safe:hover:-translate-y-px motion-safe:active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
          >
            <span aria-hidden="true" className="text-lg leading-none">+</span> New chat
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3 [scrollbar-color:var(--color-stone-300)_transparent] [scrollbar-width:thin]">
          {conversations === null && !error && (
            <ul className="mt-2 space-y-2 px-2" aria-label="Loading conversations">
              {[70, 55, 80, 45].map((w) => (
                <li key={w} className="h-4 animate-pulse rounded bg-stone-200" style={{ width: `${w}%` }} />
              ))}
            </ul>
          )}
          {error && (
            <div className="px-2 py-3 text-sm">
              <p className="text-red-700 dark:text-red-400">Could not load your conversations.</p>
              <button type="button" onClick={onRetry} className="mt-1 font-semibold text-accent-ink hover:underline">
                Try again
              </button>
            </div>
          )}
          {conversations?.length === 0 && (
            <p className="px-2 py-4 text-sm text-stone-600">No conversations yet. Ask a question to start one.</p>
          )}

          {grouped.map((group) => (
            <section key={group.name} className="mt-2">
              <h2 className="px-2 py-1 text-xs font-semibold uppercase tracking-wide text-stone-600">{group.name}</h2>
              <ul>
                {group.rows.map((c) => (
                  <ConversationRow
                    key={c.id}
                    conversation={c}
                    active={c.id === activeId}
                    onSelect={() => onSelect(c.id)}
                    onRename={() => onRename(c)}
                    onDelete={() => onDelete(c.id)}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      </nav>
    </>
  )
}

// One conversation: its title (opens it), and on hover/focus a pencil and a bin.
function ConversationRow({ conversation, active, onSelect, onRename, onDelete }) {
  const [mode, setMode] = useState('view') // 'view' | 'confirm' | 'busy'
  const [problem, setProblem] = useState(null)
  const label = conversation.title || 'Untitled chat'

  const remove = async () => {
    setMode('busy')
    try {
      await onDelete()
    } catch (e) {
      setProblem(e.message)
      setMode('view')
    }
  }

  if (mode === 'confirm' || mode === 'busy') {
    return (
      <li className="flex items-center gap-1.5 rounded-lg bg-red-50 px-2.5 py-1.5 text-sm dark:bg-red-950/40">
        <span className="min-w-0 flex-1 truncate text-red-800 dark:text-red-300">{mode === 'busy' ? 'Working...' : `Delete "${label}"?`}</span>
        <button
          type="button"
          disabled={mode === 'busy'}
          onClick={remove}
          className="rounded-md bg-red-700 px-2 py-0.5 text-xs font-semibold text-white hover:bg-red-600 disabled:opacity-50"
        >
          Delete
        </button>
        <button
          type="button"
          disabled={mode === 'busy'}
          onClick={() => setMode('view')}
          className="rounded-md px-2 py-0.5 text-xs font-semibold text-stone-700 ring-1 ring-stone-300 hover:bg-stone-100 disabled:opacity-50"
        >
          Cancel
        </button>
      </li>
    )
  }

  return (
    <li className="group relative">
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? 'page' : undefined}
        title={label}
        className={`w-full truncate rounded-lg py-2 pl-2.5 pr-16 text-left text-sm transition focus-visible:outline-2 focus-visible:outline-brand-700 ${
          active ? 'bg-surface font-medium text-accent-ink shadow-sm ring-1 ring-stone-200' : 'text-stone-700 hover:bg-stone-200/60'
        }`}
      >
        {label}
      </button>
      <span className="absolute inset-y-0 right-1 flex items-center gap-0.5 opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
        <IconButton label={`Rename "${label}"`} onClick={onRename}>
          <path d="M13.5 3.5l3 3L7 16H4v-3l9.5-9.5z" strokeLinejoin="round" />
        </IconButton>
        <IconButton label={`Delete "${label}"`} danger onClick={() => setMode('confirm')}>
          <path d="M4 6h12M8 6V4.5h4V6M6 6l.7 9.5h6.6L14 6" strokeLinecap="round" strokeLinejoin="round" />
        </IconButton>
      </span>
      {problem && <p className="px-2.5 pb-1 text-xs text-red-700 dark:text-red-400">{problem}</p>}
    </li>
  )
}

function IconButton({ label, onClick, danger = false, children }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`grid size-7 place-items-center rounded-md text-stone-600 transition focus-visible:outline-2 focus-visible:outline-brand-700 ${
        danger ? 'hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-950/60 dark:hover:text-red-400' : 'hover:bg-stone-200 hover:text-ink'
      }`}
    >
      <svg viewBox="0 0 20 20" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
        {children}
      </svg>
    </button>
  )
}
