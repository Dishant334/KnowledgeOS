import { Outlet } from 'react-router-dom'
import Header from './Header'

// The frame around every signed-in page: the top bar, then the page itself in <Outlet />.
export default function AppShell() {
  return (
    <div className="flex h-full flex-col">
      <Header />
      <main className="mx-auto min-h-0 w-full max-w-6xl flex-1 overflow-auto p-4">
        <Outlet />
      </main>
    </div>
  )
}
