import { SignUp } from '@clerk/clerk-react'
import { useTheme } from '../theme/useTheme'
import { authAppearanceFor } from './clerkAppearance'

export default function SignUpPage() {
  const { theme } = useTheme()
  return <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" appearance={authAppearanceFor(theme)} />
}
