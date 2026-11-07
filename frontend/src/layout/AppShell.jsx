import { Outlet, useLocation } from 'react-router-dom'
import Header from './Header'

// The frame around every signed-in page: the top bar, then the page itself in <Outlet />.
// The page is keyed by its address, so every route change plays the short fade-in (.page-in in index.css).
export default function AppShell() {
  const { pathname } = useLocation()

  return (
    <div className="flex h-full flex-col">
      <Header />
      <main key={pathname} className="page-in mx-auto min-h-0 w-full max-w-6xl flex-1 overflow-auto p-4">
        <Outlet />
      </main>
    </div>
  )
}
