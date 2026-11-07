import { Outlet, useLocation } from 'react-router-dom'

// The frame around every signed-in page (no top bar: the name and account menu live in the chat sidebar).
// The page is keyed by its SECTION (chat, documents, memory), so moving to another section plays the short fade-in
// (.page-in in index.css) while /chat -> /chat/12 keeps the chat mounted (its state, chips and uploads survive).
export default function AppShell() {
  const { pathname } = useLocation()
  const section = pathname.split('/')[1] || 'root'
  // The chat fills the whole window and scrolls inside its own columns; the other pages are a centred, scrolling column.
  const isChat = pathname.startsWith('/chat')

  return (
    <div className="flex h-full flex-col">
      <main key={section} className={`page-in min-h-0 w-full flex-1 ${isChat ? 'overflow-hidden' : 'mx-auto max-w-6xl overflow-auto p-4'}`}>
        <Outlet />
      </main>
    </div>
  )
}
