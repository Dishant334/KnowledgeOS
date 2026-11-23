// Every failed request reaches the screens as an ApiError, so each screen can show a message that is safe
// and readable instead of dealing with axios internals.

export class ApiError extends Error {
  constructor(message, { status = 0, retryAfter = null, code = 'error' } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status // the HTTP status; 0 means no answer at all
    this.retryAfter = retryAfter // seconds to wait (only for a 429, from the Retry-After header)
    this.code = code // 'network' | 'auth' | 'not_found' | 'too_large' | 'validation' | 'rate_limited' | 'server' | 'error'
  }
}

// "22" -> 22. Anything that is not a positive whole number -> null.
export function parseRetryAfter(value) {
  const seconds = Number.parseInt(value, 10)
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null
}

// The backend puts its message in `detail`: a string, or (for invalid input) a list of problems.
function detailText(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg
  return null
}

// axios error -> ApiError
export function toApiError(error) {
  if (error instanceof ApiError) return error

  const response = error?.response
  if (!response) {
    // No answer at all: the backend is down, VITE_API_URL is wrong, or the browser blocked the call (CORS).
    return new ApiError('Cannot reach the server. Check that the backend is running.', { code: 'network' })
  }

  const { status, data, headers } = response
  return errorFromStatus(status, data?.detail, headers?.['retry-after'])
}

// An HTTP error status (+ the backend's `detail` and the Retry-After header) -> ApiError. Shared by axios calls and
// the streaming chat call (fetch).
export function errorFromStatus(status, rawDetail, retryAfterHeader) {
  const detail = detailText(rawDetail)

  if (status === 401) return new ApiError('Your session has expired. Please sign in again.', { status, code: 'auth' })
  if (status === 404) return new ApiError(detail || 'Not found.', { status, code: 'not_found' })
  if (status === 413) return new ApiError('That file is too large (20 MB maximum).', { status, code: 'too_large' })
  if (status === 422) return new ApiError(detail || 'Some of the information is not valid.', { status, code: 'validation' })
  if (status === 429) {
    return new ApiError(detail || 'Too many requests. Please slow down.', {
      status,
      code: 'rate_limited',
      retryAfter: parseRetryAfter(retryAfterHeader),
    })
  }
  if (status >= 500) return new ApiError(detail || 'The server had a problem. Please try again.', { status, code: 'server' })
  return new ApiError(detail || `The request failed (${status}).`, { status })
}
