import { ClerkProvider } from '@clerk/clerk-react'
import { useNavigate } from 'react-router-dom'
import { CLERK_PUBLISHABLE_KEY } from '../lib/constants'

// Clerk's provider, told to use React Router for its own navigation (so signing in does not reload the page).
export default function ClerkWithRouter({ children }) {
  const navigate = useNavigate()

  return (
    <ClerkProvider
      publishableKey={CLERK_PUBLISHABLE_KEY}
      routerPush={(to) => navigate(to)}
      routerReplace={(to) => navigate(to, { replace: true })}
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      signInFallbackRedirectUrl="/chat"
      signUpFallbackRedirectUrl="/chat"
      afterSignOutUrl="/sign-in"
    >
      {children}
    </ClerkProvider>
  )
}
