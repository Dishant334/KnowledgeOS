import { SignIn } from '@clerk/clerk-react'

// Clerk draws the whole sign-in form (email, password, social logins, errors...).
export default function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <SignIn routing="path" path="/sign-in" signUpUrl="/sign-up" />
    </div>
  )
}
