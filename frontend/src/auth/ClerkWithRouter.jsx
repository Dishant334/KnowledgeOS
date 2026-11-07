import { ClerkProvider } from '@clerk/clerk-react'
import { useNavigate } from 'react-router-dom'
import { CLERK_PUBLISHABLE_KEY } from '../lib/constants'
import { clerkVariables } from './clerkAppearance'

// The wording on the first screen of each form (Clerk's defaults are "Sign in to <app>" / "Create your account").
// The "Combined" keys are used when email and password share one screen.
const localization = {
  signIn: {
    start: {
      title: 'Welcome back',
      titleCombined: 'Welcome back',
      subtitle: 'Sign in to continue to KnowledgeOS.',
      subtitleCombined: 'Sign in to continue to KnowledgeOS.',
    },
  },
  signUp: {
    start: {
      title: 'Create your account',
      titleCombined: 'Create your account',
      subtitle: 'Start asking questions about your own documents.',
      subtitleCombined: 'Start asking questions about your own documents.',
    },
  },
}

// Puts all of Clerk's own CSS into a layer named "clerk" that sits below Tailwind's utilities (see the @layer line
// in index.css), so the Tailwind classes we hand to Clerk (clerkAppearance.js) are not overridden by Clerk's styles.
// `variables` gives everything Clerk draws anywhere (for example the account menu in the top bar) our colours.
const appearance = { cssLayerName: 'clerk', variables: clerkVariables }

// Clerk's provider, told to use React Router for its own navigation (so signing in does not reload the page).
export default function ClerkWithRouter({ children }) {
  const navigate = useNavigate()

  return (
    <ClerkProvider
      publishableKey={CLERK_PUBLISHABLE_KEY}
      appearance={appearance}
      localization={localization}
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
