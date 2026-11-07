import { UserButton } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'

// The left column: New chat, then the conversations grouped by day. On phones it is a drawer that slides in over the chat.
// Rename/delete buttons will appear on hover once the list is connected (looks only for now).
export default function ConversationSidebar({ open, onClose, activeId, onSelect, conversations = [] }) {
  const groups = [...new Set(conversations.map((c) => c.group))]

  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-ink/40 md:hidden" onClick={onClose} aria-hidden="true" />}
      <nav
        aria-label="Conversations"
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-stone-200 bg-stone-50 transition-transform duration-300 md:static md:z-auto md:w-72 md:shrink-0 md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
          <Link to="/chat" className="font-display text-xl font-semibold tracking-tight text-brand-800">
            KnowledgeOS
          </Link>
          <UserButton />
        </div>

        <div className="p-3">
          <button
            type="button"
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-700 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-brand-800 motion-safe:hover:-translate-y-px motion-safe:active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
          >
            <span aria-hidden="true" className="text-lg leading-none">+</span> New chat
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
          {conversations.length === 0 && (
            <p className="px-2 py-4 text-sm text-stone-600">No conversations yet.</p>
          )}
          {groups.map((group) => (
            <section key={group} className="mt-2">
              <h2 className="px-2 py-1 text-xs font-semibold uppercase tracking-wide text-stone-600">{group}</h2>
              <ul>
                {conversations.filter((c) => c.group === group).map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(c.id)}
                      aria-current={c.id === activeId ? 'page' : undefined}
                      className={`w-full truncate rounded-lg px-2.5 py-2 text-left text-sm transition focus-visible:outline-2 focus-visible:outline-brand-700 ${
                        c.id === activeId
                          ? 'bg-white font-medium text-brand-800 shadow-sm ring-1 ring-stone-200'
                          : 'text-stone-700 hover:bg-stone-200/60'
                      }`}
                    >
                      {c.title}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </nav>
    </>
  )
}
