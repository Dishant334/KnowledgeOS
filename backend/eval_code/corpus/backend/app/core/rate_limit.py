# app/core/rate_limit.py
"""
Rate limiting: protects the expensive parts of the API (/ask costs LLM time and, through the
Gemini fallback, free-tier quota; uploads cost embedding work) from one user, a bug or a script.

TWO ALGORITHMS, both keeping their state in Redis (so it survives restarts and is shared by every
server process, unlike a Python variable):

1. TOKEN BUCKET  ("10 questions per minute")
   A bucket holds up to `capacity` tokens. Every request takes one; an empty bucket means "no".
   Tokens flow back at a steady rate (capacity / period). Nothing runs on a timer: when a request
   arrives we work out how many tokens would have flowed back since the last visit:

       tokens = min(capacity, tokens + seconds_since_last_visit * refill_rate)

   It allows a short burst (up to `capacity`) and then smooths out, and it knows exactly how long a
   rejected caller must wait. A plain "N per minute" counter would let someone send N requests at
   0:59 and N more at 1:01.

2. FIXED-WINDOW COUNTER  ("100 questions per day")
   One counter per user per UTC day. At the limit, "no"; the key expires at the next UTC midnight, so
   it resets by itself. Its weakness (a burst around midnight can use two days' budget at once) does
   not matter for a safety net.

WHY LUA: "read the bucket, refill it, take a token, write it back" must happen as ONE step. Done from
Python in separate calls, two simultaneous requests could both see "1 token left" and both take it.
Redis runs a Lua script without interleaving anything else, and in a single network round trip.

FAIL OPEN: if Redis is down or slow the request is allowed (and a warning is logged). The limiter is
a safety net; it must never be the reason the API is unavailable.
"""

import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import redis
from fastapi import Depends, HTTPException, status

from app.core.config import settings
from app.db.models.user import User
from app.dependencies.auth import get_current_user

logger = logging.getLogger(__name__)

# Redis is local and fast; if it does not answer within this time we treat it as down.
REDIS_TIMEOUT_SECONDS = 0.25

# KEYS[1] = the bucket (a Redis hash with the fields "tokens" and "ts")
# ARGV[1] = capacity, ARGV[2] = tokens that flow back per second
# Returns {allowed (1/0), seconds to wait before one token is available, tokens left}.
TOKEN_BUCKET_LUA = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])

local time = redis.call('TIME')                         -- Redis's own clock: {seconds, microseconds}
local now = tonumber(time[1]) + tonumber(time[2]) / 1000000

local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local last = tonumber(data[2])
if tokens == nil then                                   -- first visit: a full bucket
  tokens = capacity
  last = now
end

tokens = math.min(capacity, tokens + math.max(0, now - last) * rate)    -- refill

local allowed = 0
local wait = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait = (1 - tokens) / rate
end

redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / rate) + 1)   -- an idle bucket is full again by then
return {allowed, tostring(wait), tostring(tokens)}
"""

# KEYS[1] = today's counter, ARGV[1] = the limit, ARGV[2] = seconds until the counter should vanish
# Returns {allowed (1/0), the count so far}. A denied request does NOT increase the count.
DAILY_COUNTER_LUA = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current >= tonumber(ARGV[1]) then
  return {0, current}
end
current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
return {1, current}
"""


@dataclass
class Decision:
    """The verdict for one check."""

    allowed: bool
    retry_after: int = 0     # seconds to wait before trying again (only when denied)
    limit: int = 0           # the limit that applied (for the X-RateLimit-Limit header)
    message: str = ""        # what the client is told (only when denied)


@lru_cache(maxsize=1)
def _client() -> redis.Redis:
    """One shared connection pool, created on first use (importing this module connects to nothing)."""
    return redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
        decode_responses=True,
    )


@lru_cache(maxsize=1)
def _scripts():
    """The Lua scripts, registered once. redis-py sends the cheap EVALSHA and loads the script if Redis lacks it."""
    client = _client()
    return client.register_script(TOKEN_BUCKET_LUA), client.register_script(DAILY_COUNTER_LUA)


def seconds_until_utc_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, math.ceil((midnight - now).total_seconds()))


def take_token(key: str, capacity: int, period_seconds: int, what: str) -> Decision:
    """
    Token bucket: allow `capacity` requests per `period_seconds` (refilling steadily), per `key`.
    `what` names the thing being limited in the message ("questions", "uploads").
    """
    try:
        bucket, _ = _scripts()
        allowed, wait, *_ = bucket(keys=[key], args=[capacity, capacity / period_seconds])
    except (redis.RedisError, OSError):
        logger.warning("Rate limiter: Redis is unavailable, letting the request through", exc_info=True)
        return Decision(allowed=True)

    if int(allowed) == 1:
        return Decision(allowed=True, limit=capacity)

    seconds = max(1, math.ceil(float(wait)))
    return Decision(
        allowed=False,
        retry_after=seconds,
        limit=capacity,
        message=f"Too many {what}. Try again in {seconds} seconds.",
    )


def count_today(key_prefix: str, limit: int, what: str) -> Decision:
    """Fixed-window counter: allow `limit` requests per UTC day, per `key_prefix` (the date is added to the key)."""
    now = datetime.now(timezone.utc)
    key = f"{key_prefix}:{now:%Y%m%d}"
    reset_in = seconds_until_utc_midnight(now)
    try:
        _, counter = _scripts()
        allowed, *_ = counter(keys=[key], args=[limit, reset_in])
    except (redis.RedisError, OSError):
        logger.warning("Rate limiter: Redis is unavailable, letting the request through", exc_info=True)
        return Decision(allowed=True)

    if int(allowed) == 1:
        return Decision(allowed=True, limit=limit)

    return Decision(
        allowed=False,
        retry_after=reset_in,
        limit=limit,
        message=f"Daily limit of {limit} {what} reached. It resets at 00:00 UTC.",
    )


def reject(decision: Decision) -> None:
    """Turns a denial into the HTTP 429 the client sees. Retry-After is the standard header for "come back in N seconds"."""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=decision.message,
        headers={
            "Retry-After": str(decision.retry_after),
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Reset": str(int(time.time()) + decision.retry_after),   # unix time when it is allowed again
        },
    )


# --- FastAPI dependencies -------------------------------------------------------------------------
# They depend on get_current_user, so they run AFTER login and can key on the user (an unauthenticated
# request is a 401 first). FastAPI caches get_current_user per request, so the user is not looked up twice.


def limit_ask(current_user: User = Depends(get_current_user)) -> None:
    """/ask and /ask/stream share one budget: per-minute burst first, then the daily cap."""
    if not settings.rate_limit_enabled:
        return

    # Burst before daily: someone hammering past the burst limit never spends daily budget.
    burst = take_token(f"rl:ask:burst:{current_user.id}", settings.ask_per_minute, 60, "questions")
    if not burst.allowed:
        reject(burst)

    daily = count_today(f"rl:ask:day:{current_user.id}", settings.ask_per_day, "questions")
    if not daily.allowed:
        reject(daily)


def limit_upload(current_user: User = Depends(get_current_user)) -> None:
    """Document uploads (each one triggers embedding work): a token bucket per hour."""
    if not settings.rate_limit_enabled:
        return

    uploads = take_token(f"rl:upload:{current_user.id}", settings.upload_per_hour, 3600, "uploads")
    if not uploads.allowed:
        reject(uploads)
