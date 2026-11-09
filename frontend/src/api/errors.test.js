// Unit tests for api/errors.js: every failed request must become a safe, readable ApiError.
//
// The shape of a test file:
//   describe('a group', () => { it('one behaviour, in words', () => { ...run code...; expect(result).toBe(...) }) })
// `expect(x)` + a matcher (toBe, toEqual, toMatch, toBeNull...) is the check. A test fails when a check fails.
import { describe, expect, it } from 'vitest'
import { ApiError, errorFromStatus, parseRetryAfter, toApiError } from './errors'

describe('parseRetryAfter', () => {
  it('reads a number of seconds', () => {
    expect(parseRetryAfter('22')).toBe(22)
  })

  // it.each runs the same test for every row: one line per case instead of one test per case
  it.each([[undefined], [null], [''], ['abc'], ['0'], ['-5']])('returns null for %j', (value) => {
    expect(parseRetryAfter(value)).toBeNull()
  })
})

describe('errorFromStatus', () => {
  it('a 401 asks the user to sign in again', () => {
    const error = errorFromStatus(401, 'Invalid token signature')
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe('auth')
    // the backend's technical reason is NOT shown for a 401
    expect(error.message).toBe('Your session has expired. Please sign in again.')
  })

  it('a 429 carries the wait time from Retry-After', () => {
    const error = errorFromStatus(429, 'Too many questions', '12')
    expect(error).toMatchObject({ status: 429, code: 'rate_limited', retryAfter: 12, message: 'Too many questions' })
  })

  it('a 429 without a usable Retry-After has no wait time', () => {
    expect(errorFromStatus(429, undefined, 'soon').retryAfter).toBeNull()
  })

  it('a 413 says the file is too large, whatever the server wrote', () => {
    expect(errorFromStatus(413, 'Request Entity Too Large').message).toBe('That file is too large (20 MB maximum).')
  })

  it('a 422 shows the first problem of a validation list', () => {
    const detail = [{ loc: ['body', 'title'], msg: 'String should have at least 1 character' }]
    expect(errorFromStatus(422, detail)).toMatchObject({ code: 'validation', message: 'String should have at least 1 character' })
  })

  it('uses a friendly default when the server sends no detail', () => {
    expect(errorFromStatus(404).message).toBe('Not found.')
    expect(errorFromStatus(503).message).toBe('The server had a problem. Please try again.')
    expect(errorFromStatus(418).message).toBe('The request failed (418).')
  })

  it('ignores a detail that is not text (an object is never shown raw)', () => {
    expect(errorFromStatus(500, { trace: 'File "/srv/app/x.py", line 3' }).message).toBe('The server had a problem. Please try again.')
  })
})

describe('toApiError', () => {
  it('no response at all means the server cannot be reached', () => {
    const error = toApiError(new Error('Network Error'))
    expect(error.code).toBe('network')
    expect(error.status).toBe(0)
  })

  it('reads status, detail and the Retry-After header of an axios error', () => {
    const axiosError = { response: { status: 429, data: { detail: 'Slow down' }, headers: { 'retry-after': '30' } } }
    expect(toApiError(axiosError)).toMatchObject({ code: 'rate_limited', retryAfter: 30, message: 'Slow down' })
  })

  it('passes an ApiError through unchanged', () => {
    const original = new ApiError('x', { code: 'auth' })
    expect(toApiError(original)).toBe(original) // toBe = the very same object
  })
})
