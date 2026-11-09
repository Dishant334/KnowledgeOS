// Unit tests for askStream: reading the streamed answer of POST /ask/stream.
// No backend runs here. `fetch` is replaced by a fake that returns whatever stream each test builds, which lets us
// test cases that are hard to produce for real: an event split across two network chunks, a stream cut off halfway.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { askStream } from './askStream'

// vi.mock replaces a module for every import in this file (Vitest moves this call to the top, before the imports).
// The real client.js would ask Clerk for a token; the fake answers at once.
vi.mock('./client', () => ({
  api: { defaults: { baseURL: 'http://api.test' } },
  getAuthToken: vi.fn(async () => 'test-token'),
}))

// A fake HTTP response whose body arrives in the given chunks (like packets over the network).
function streamResponse(chunks, init = {}) {
  const encoder = new TextEncoder()
  const body = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' }, ...init })
}

const sse = (event, data) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
const DONE = { answer: 'Employees get 25 days [1].', citations: [], conversation_id: 'abc', abstained: false }

let fetchMock
beforeEach(() => {
  fetchMock = vi.fn() // vi.fn() = a fake function that records every call made to it
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('askStream', () => {
  it('sends the question with the token and returns the saved answer', async () => {
    fetchMock.mockResolvedValue(streamResponse([sse('token', { text: 'Employees ' }), sse('token', { text: 'get 25 days.' }), sse('done', DONE)]))
    const tokens = []

    const result = await askStream({ query: 'Vacation?', conversationId: 'abc', onToken: (t) => tokens.push(t) })

    expect(tokens).toEqual(['Employees ', 'get 25 days.'])
    expect(result).toEqual(DONE)
    // check HOW fetch was called: the address, the token header and the JSON body
    const [url, options] = fetchMock.mock.calls[0]
    expect(url).toBe('http://api.test/ask/stream')
    expect(options.method).toBe('POST')
    expect(options.headers.Authorization).toBe('Bearer test-token')
    expect(JSON.parse(options.body)).toEqual({ query: 'Vacation?', conversation_id: 'abc' })
  })

  it('a new chat sends conversation_id null', async () => {
    fetchMock.mockResolvedValue(streamResponse([sse('done', DONE)]))
    await askStream({ query: 'hi' })
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).conversation_id).toBeNull()
  })

  it('joins an event that arrives split across network chunks', async () => {
    const whole = sse('token', { text: 'Hello' }) + sse('done', DONE)
    // cut the text in odd places, even inside the JSON
    fetchMock.mockResolvedValue(streamResponse([whole.slice(0, 9), whole.slice(9, 30), whole.slice(30)]))
    const tokens = []
    await askStream({ query: 'q', onToken: (t) => tokens.push(t) })
    expect(tokens).toEqual(['Hello'])
  })

  it('skips a broken event and keeps going', async () => {
    fetchMock.mockResolvedValue(streamResponse(['event: token\ndata: {not json\n\n', sse('token', { text: 'ok' }), sse('done', DONE)]))
    const tokens = []
    await askStream({ query: 'q', onToken: (t) => tokens.push(t) })
    expect(tokens).toEqual(['ok'])
  })

  // `await expect(promise).rejects...` checks that an async call FAILS in the expected way
  it('an HTTP error before the first token becomes an ApiError (429 with the wait time)', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Too many questions' }), { status: 429, headers: { 'Retry-After': '20' } }),
    )
    await expect(askStream({ query: 'q' })).rejects.toMatchObject({ code: 'rate_limited', retryAfter: 20, message: 'Too many questions' })
  })

  it('an error event after tokens started is thrown', async () => {
    fetchMock.mockResolvedValue(streamResponse([sse('token', { text: 'Half' }), sse('error', { status: 503, detail: 'Model unavailable' })]))
    await expect(askStream({ query: 'q' })).rejects.toMatchObject({ status: 503, message: 'Model unavailable' })
  })

  it('a stream that ends without "done" counts as cut off', async () => {
    fetchMock.mockResolvedValue(streamResponse([sse('token', { text: 'Half an ans' })]))
    await expect(askStream({ query: 'q' })).rejects.toThrow('The answer was cut off. Please try again.')
  })

  it('no connection at all gives a "cannot reach the server" error', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(askStream({ query: 'q' })).rejects.toMatchObject({ code: 'network' })
  })

  it('Stop (abort) is passed through as an AbortError, not turned into a server error', async () => {
    fetchMock.mockRejectedValue(new DOMException('The user aborted a request.', 'AbortError'))
    await expect(askStream({ query: 'q', signal: new AbortController().signal })).rejects.toMatchObject({ name: 'AbortError' })
  })
})
