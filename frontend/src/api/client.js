import axios from 'axios'
import { API_URL } from '../lib/constants'
import { toApiError } from './errors'

// The Clerk session token. Clerk puts itself on window.Clerk once it has loaded; the signed-in pages only
// render after that (see auth/RequireAuth.jsx), so no request starts without it. getToken() returns a cached
// token and refreshes it by itself when it is about to expire.
let lastToken = null

export async function getAuthToken() {
  lastToken = (await window.Clerk?.session?.getToken()) ?? null
  return lastToken
}

// The token used by the most recent request, without waiting (for a request sent while the page closes).
export function peekAuthToken() {
  return lastToken
}

// One axios instance for every JSON, upload and delete call. (The streaming chat call uses fetch: see api/askStream.js.)
export const api = axios.create({ baseURL: API_URL, timeout: 30000 })

// Before each request: attach "Authorization: Bearer <token>".
api.interceptors.request.use(async (config) => {
  const token = await getAuthToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// After each response: failures become an ApiError (a request that was cancelled on purpose stays as it is).
api.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(axios.isCancel(error) ? error : toApiError(error)),
)
