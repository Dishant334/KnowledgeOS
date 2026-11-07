import { SignUp } from '@clerk/clerk-react'
import { authAppearance } from './clerkAppearance'

export default function SignUpPage() {
  return <SignUp routing="path" path="/sign-up" signInUrl="/sign-in" appearance={authAppearance} />
}
