import { useUser } from '@clerk/clerk-react'
import { useEffect, useState } from 'react'
import { getMe } from '../api/users'
import Button from '../components/Button'
import ErrorBanner from '../components/ErrorBanner'
import Spinner from '../components/Spinner'

// TEMPORARY page for build step 1 (chat replaces it in step 3). It proves the whole chain works:
// Clerk login -> token on the request -> CORS -> backend verifies the token -> your user comes back.
export default function AccountCheckPage() {
  const { user } = useUser()
  const [result, setResult] = useState({ status: 'loading', me: null, error: null })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let ignore = false // a newer attempt (or leaving the page) makes this one's answer irrelevant
    getMe().then(
      (me) => !ignore && setResult({ status: 'ok', me, error: null }),
      (error) => !ignore && setResult({ status: 'error', me: null, error }),
    )
    return () => {
      ignore = true
    }
  }, [attempt])

  function retry() {
    setResult({ status: 'loading', me: null, error: null })
    setAttempt((n) => n + 1)
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-xl font-semibold">Welcome{user?.firstName ? `, ${user.firstName}` : ''}</h1>

      <section className="rounded-lg border border-stone-200 bg-white p-5">
        <h2 className="text-sm font-medium text-stone-600">Backend connection</h2>

        {result.status === 'loading' && <Spinner label="Asking the backend who you are..." className="mt-3 justify-start" />}

        {result.status === 'ok' && (
          <div className="mt-3 space-y-1 text-sm">
            <p className="font-medium text-green-700">Connected: the backend recognises you.</p>
            <p className="text-stone-600">Name: {result.me.name || '(not set)'}</p>
            <p className="text-stone-600">Email: {result.me.email || '(not set)'}</p>
            <p className="text-stone-600">Backend user id: {result.me.id}</p>
          </div>
        )}

        {result.status === 'error' && (
          <div className="mt-3">
            <ErrorBanner message={result.error.message} action={<Button variant="secondary" onClick={retry}>Try again</Button>} />
          </div>
        )}
      </section>

      <p className="text-sm text-stone-600">
        Build step 1 of the frontend is in place: login, protected pages and the API client. Documents, chat and memory come in
        the next steps.
      </p>
    </div>
  )
}
