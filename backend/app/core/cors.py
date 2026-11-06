# app/core/cors.py
"""
CORS: lets a browser app served from another address (for example the Vite dev server on
http://localhost:5173) call this API.

A browser only lets a page read responses from ANOTHER origin when the API says so with CORS headers.
Without them every request from the frontend is blocked by the browser, even though the API is fine.

Choices made here:
  * Only the origins listed in CORS_ORIGINS are allowed (no "*"), so other websites cannot call the API
    from a user's browser.
  * No cookies: the frontend sends its Clerk token in the Authorization header, so credentials stay off.
  * Retry-After and X-RateLimit-* are EXPOSED. Browsers hide all non-standard response headers from
    JavaScript unless they are listed, and the frontend needs Retry-After to show "try again in N seconds".
  * An empty CORS_ORIGINS turns CORS off (the right setting when the frontend is served from the same origin).
"""

ALLOWED_METHODS = ["GET", "POST", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = ["Authorization", "Content-Type"]
EXPOSED_HEADERS = ["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Reset"]


def parse_origins(value: str) -> list[str]:
    """"http://a.com, http://b.com/" -> ["http://a.com", "http://b.com"] (browsers send origins without a trailing slash)."""
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


def cors_options(cors_origins: str) -> dict | None:
    """Keyword arguments for Starlette's CORSMiddleware, or None when no origin is configured."""
    origins = parse_origins(cors_origins)
    if not origins:
        return None
    return {
        "allow_origins": origins,
        "allow_credentials": False,
        "allow_methods": ALLOWED_METHODS,
        "allow_headers": ALLOWED_HEADERS,
        "expose_headers": EXPOSED_HEADERS,
        "max_age": 600,                      # the browser may cache a preflight answer for 10 minutes
    }
