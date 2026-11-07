import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-4 text-center">
      <p className="text-5xl font-semibold text-stone-300">404</p>
      <h1 className="text-lg font-medium">This page does not exist</h1>
      <Link to="/chat" className="text-sm font-medium text-brand-600 hover:underline">
        Back to the app
      </Link>
    </div>
  )
}
