import { SignIn } from '@clerk/clerk-react'
import { authAppearance } from './clerkAppearance'

// Clerk draws the whole sign-in form (email, password, social logins, errors...). The card around it is AuthLayout.
export default function SignInPage() {
  return <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" appearance={authAppearance} />
}
