import { UserButton } from '@clerk/clerk-react'
import { Link, NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/chat', label: 'Chat' },
  { to: '/documents', label: 'Documents' },
  { to: '/memory', label: 'Memory' },
]

// The top bar on every signed-in page: name, the three sections, and Clerk's account menu (profile, sign out).
// Each link has an underline that grows from the left on hover and stays under the page you are on.
export default function Header() {
  return (
    <header className="border-b border-stone-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-8">
          <Link to="/chat" className="font-display text-xl font-semibold tracking-tight text-brand-800">
            KnowledgeOS
          </Link>
          <nav className="flex gap-1">
            {LINKS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `relative rounded-md px-3 py-1.5 text-sm font-medium transition-colors after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:origin-left after:rounded-full after:bg-highlight after:transition-transform after:duration-300 hover:text-brand-800 hover:after:scale-x-100 ${
                    isActive ? 'text-brand-800 after:scale-x-100' : 'text-stone-600 after:scale-x-0'
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
