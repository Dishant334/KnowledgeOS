import { api, getAuthToken } from './client'
import { ApiError, errorFromStatus } from './errors'

// POST /ask/stream: the answer arrives word by word as server-sent events.
//   event: token  data: {"text": "..."}        a piece of the answer
//   event: done   data: <AskResponse>           once, after the turn is saved (its `answer` is the one to trust)
//   event: error  data: {"status", "detail"}    something failed after tokens had started (nothing was saved)
//
// This is the one call that uses fetch: axios cannot read a response body as a stream in the browser, and the
// browser's EventSource cannot send a POST or an Authorization header.
// A problem BEFORE the first token is a normal HTTP error (401/404/429/503...) and is thrown as an ApiError, like
// every axios call. Cancel with `signal` (the Stop button): an AbortError is thrown and the backend saves nothing.
export async function askStream({ query, conversationId, onToken, signal }) {
  const token = await getAuthToken()
  let response
  try {
    response = await fetch(`${api.defaults.baseURL}/ask/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ query, conversation_id: conversationId ?? null }),
      signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new ApiError('Cannot reach the server. Check that the backend is running.', { code: 'network' })
  }

  if (!response.ok) {
    let body = null
    try {
      body = await response.json()
    } catch {
      /* not JSON */
    }
    throw errorFromStatus(response.status, body?.detail, response.headers.get('retry-after'))
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let done = null

  for (;;) {
    const { value, done: finished } = await reader.read()
    if (finished) break
    buffer += decoder.decode(value, { stream: true })
    // events are separated by a blank line; keep an unfinished one in the buffer
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const event = parseEvent(block)
      if (!event) continue
      if (event.type === 'token') onToken?.(event.data.text ?? '')
      else if (event.type === 'done') done = event.data
      else if (event.type === 'error') throw errorFromStatus(event.data.status ?? 500, event.data.detail)
    }
  }

  if (!done) throw new ApiError('The answer was cut off. Please try again.', { code: 'server' })
  return done
}

// "event: token\ndata: {...}" -> { type, data }
function parseEvent(block) {
  let type = 'message'
  const data = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) type = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!data.length) return null
  try {
    return { type, data: JSON.parse(data.join('\n')) }
  } catch {
    return null
  }
}
