import { Outlet, useLocation } from 'react-router-dom'

// The frame around the signed-in app (the chat is its only page; the name and account menu live in its sidebar).
// The chat fills the whole window and scrolls inside its own columns. The page is keyed by its SECTION, so
// /chat -> /chat/<id> keeps the chat mounted (its state, chips and uploads survive) and only a new section fades in.
export default function AppShell() {
  const { pathname } = useLocation()
  const section = pathname.split('/')[1] || 'root'

  return (
    <div className="flex h-full flex-col">
      <main key={section} className="page-in min-h-0 w-full flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
