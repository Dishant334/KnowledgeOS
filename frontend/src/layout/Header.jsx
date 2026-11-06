import { UserButton } from '@clerk/clerk-react'
import { Link, NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/chat', label: 'Chat' },
  { to: '/documents', label: 'Documents' },
  { to: '/memory', label: 'Memory' },
]

// The top bar on every signed-in page: name, the three sections, and Clerk's account menu (profile, sign out).
export default function Header() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-8">
          <Link to="/chat" className="text-lg font-semibold tracking-tight text-indigo-700">
            KnowledgeOS
          </Link>
          <nav className="flex gap-1">
            {LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm font-medium ${
                    isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
        <UserButton />
      </div>
    </header>
  )
}
