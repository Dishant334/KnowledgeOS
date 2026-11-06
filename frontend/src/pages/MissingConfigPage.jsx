// Shown instead of a blank screen when frontend/.env has no Clerk key.
export default function MissingConfigPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="max-w-lg rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
        <h1 className="text-base font-semibold">One setting is missing</h1>
        <p className="mt-2">
          The app needs your Clerk publishable key to show the login. Copy <code>frontend/.env.example</code> to{' '}
          <code>frontend/.env</code>, set <code>VITE_CLERK_PUBLISHABLE_KEY</code> (Clerk dashboard, API keys, the key that starts
          with <code>pk_</code>), then restart <code>npm run dev</code>.
        </p>
      </div>
    </div>
  )
}
