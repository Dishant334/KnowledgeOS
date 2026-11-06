import { useAuth } from '@clerk/clerk-react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import Spinner from '../components/Spinner'

// Wraps every page that needs a login. Signed-out visitors are sent to /sign-in and, after signing in,
// Clerk returns them to the page they asked for (that is what the redirect_url parameter is for).
export default function RequireAuth() {
  const { isLoaded, isSignedIn } = useAuth()
  const location = useLocation()

  if (!isLoaded) return <Spinner label="Loading..." className="h-screen" />

  if (!isSignedIn) {
    const back = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/sign-in?redirect_url=${back}`} replace />
  }

  return <Outlet />
}
