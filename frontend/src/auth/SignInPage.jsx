import { SignIn } from '@clerk/clerk-react'
import { useTheme } from '../theme/useTheme'
import { authAppearanceFor } from './clerkAppearance'

// Clerk draws the whole sign-in form (email, password, social logins, errors...). The card around it is AuthLayout.
export default function SignInPage() {
  const { theme } = useTheme()
  return <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" appearance={authAppearanceFor(theme)} />
}
