"""
Rate limiting (app/core/rate_limit.py).

REAL Redis (the isolated test DB 15), so the Lua scripts really run. Every key the limiter writes starts
with "rl:", and these tests delete only those keys (never flushdb: other tests leave data in DB 15).
The HTTP tests use the real app with a fake LLM, like test_retrieve_ask_api.py.
"""

import time
import uuid
from datetime import datetime, timezone

import pytest
import redis

from app.core import rate_limit
from app.core.config import settings
from app.db.models import Conversation, Message
from tests.conftest import make_fake_llm
from tests.test_ask_stream import make_streaming_llm
from tests.test_retrieve_ask_api import headers_for, use_llm, users  # noqa: F401  (shared fixtures)

QUESTION = "How many vacation days do employees get?"
PDF = "application/pdf"


def _delete_limiter_keys():
    client = rate_limit._client()
    for key in client.scan_iter("rl:*"):
        client.delete(key)


@pytest.fixture(autouse=True)
def clean_redis():
    _delete_limiter_keys()
    yield
    _delete_limiter_keys()


@pytest.fixture
def limits(monkeypatch):
    """Turns limiting on (tests run with it off) with generous defaults; limits(ask_per_minute=3) overrides some."""
    monkeypatch.setattr(settings, "rate_limit_enabled", True)

    def set_limits(**values):
        for name, value in values.items():
            monkeypatch.setattr(settings, name, value)

    set_limits(ask_per_minute=100, ask_per_day=1000, upload_per_hour=100)
    return set_limits


def unique_key():
    return f"rl:test:{uuid.uuid4().hex}"


# --- token bucket ---------------------------------------------------------------------------------------


def test_bucket_allows_exactly_its_capacity_then_denies_with_a_wait_time():
    key = unique_key()
    verdicts = [rate_limit.take_token(key, 3, 60, "questions") for _ in range(4)]

    assert [v.allowed for v in verdicts] == [True, True, True, False]
    denied = verdicts[-1]
    assert 1 <= denied.retry_after <= 20                      # 3 tokens per 60 s = one token every 20 s
    assert denied.limit == 3 and "Too many questions" in denied.message and "seconds" in denied.message


def test_bucket_refills_over_time():
    key = unique_key()
    assert rate_limit.take_token(key, 2, 1, "x").allowed and rate_limit.take_token(key, 2, 1, "x").allowed
    assert not rate_limit.take_token(key, 2, 1, "x").allowed        # empty; refills at 2 tokens per second

    time.sleep(0.7)                                                  # about 1.4 tokens came back
    assert rate_limit.take_token(key, 2, 1, "x").allowed


def test_bucket_never_holds_more_than_its_capacity():
    key = unique_key()
    rate_limit.take_token(key, 2, 1, "x")
    time.sleep(1.5)                                                  # idle long enough to refill many times over

    verdicts = [rate_limit.take_token(key, 2, 1, "x").allowed for _ in range(3)]
    assert verdicts == [True, True, False]                           # capacity 2, not 3


def test_an_idle_bucket_expires_from_redis():
    key = unique_key()
    rate_limit.take_token(key, 3, 60, "x")
    assert 0 < rate_limit._client().ttl(key) <= 61                    # cleaned up once it would be full again


def test_buckets_are_independent_per_key():
    a, b = unique_key(), unique_key()
    for _ in range(2):
        rate_limit.take_token(a, 2, 60, "x")
    assert not rate_limit.take_token(a, 2, 60, "x").allowed
    assert rate_limit.take_token(b, 2, 60, "x").allowed


# --- daily counter --------------------------------------------------------------------------------------


def test_daily_counter_denies_at_the_limit_and_does_not_count_denials():
    prefix = unique_key()
    verdicts = [rate_limit.count_today(prefix, 3, "questions") for _ in range(5)]

    assert [v.allowed for v in verdicts] == [True, True, True, False, False]
    today = f"{datetime.now(timezone.utc):%Y%m%d}"
    assert rate_limit._client().get(f"{prefix}:{today}") == "3"      # the two denials were not counted
    denied = verdicts[-1]
    assert "Daily limit of 3 questions" in denied.message and "00:00 UTC" in denied.message
    assert 1 <= denied.retry_after <= 86400


def test_daily_counter_key_expires_at_the_next_utc_midnight():
    prefix = unique_key()
    rate_limit.count_today(prefix, 3, "questions")
    today = f"{datetime.now(timezone.utc):%Y%m%d}"
    ttl = rate_limit._client().ttl(f"{prefix}:{today}")
    assert 0 < ttl <= 86400
    assert abs(ttl - rate_limit.seconds_until_utc_midnight()) <= 2


def test_seconds_until_utc_midnight():
    assert rate_limit.seconds_until_utc_midnight(datetime(2026, 11, 5, 23, 59, 30, tzinfo=timezone.utc)) == 30
    assert rate_limit.seconds_until_utc_midnight(datetime(2026, 11, 5, 0, 0, 0, tzinfo=timezone.utc)) == 86400


# --- Redis down: fail open ------------------------------------------------------------------------------


def test_the_limiter_fails_open_and_logs_when_redis_is_unavailable(monkeypatch, caplog):
    def broken():
        raise redis.ConnectionError("redis is down")

    monkeypatch.setattr(rate_limit, "_scripts", broken)
    # Tests that run Alembic migrations call logging.config.fileConfig, whose default silently DISABLES every
    # logger that already exists (ours included). Switch it back on so caplog sees the warning in any test order.
    monkeypatch.setattr(rate_limit.logger, "disabled", False)

    with caplog.at_level("WARNING"):
        assert rate_limit.take_token(unique_key(), 1, 60, "x").allowed
        assert rate_limit.count_today(unique_key(), 1, "x").allowed
    assert "Redis is unavailable" in caplog.text


# --- /ask over HTTP -------------------------------------------------------------------------------------


def ask(client, user, path="/ask"):
    return client.post(path, headers=headers_for(user), json={"query": QUESTION})


def test_ask_over_the_per_minute_limit_is_429_with_retry_after(client, users, use_llm, limits, db):
    use_llm(make_fake_llm())
    limits(ask_per_minute=3)

    assert [ask(client, users[0]).status_code for _ in range(3)] == [200, 200, 200]
    resp = ask(client, users[0])

    assert resp.status_code == 429
    assert "Too many questions" in resp.json()["detail"]
    assert 1 <= int(resp.headers["Retry-After"]) <= 20
    assert resp.headers["X-RateLimit-Limit"] == "3"
    assert int(resp.headers["X-RateLimit-Reset"]) >= int(time.time())
    assert db.query(Message).count() == 6                            # the rejected question saved nothing


def test_a_rejected_ask_never_reaches_the_llm(client, users, use_llm, limits):
    calls = []
    use_llm(make_fake_llm(calls=calls))
    limits(ask_per_minute=1)

    assert ask(client, users[0]).status_code == 200
    seen = len(calls)
    assert ask(client, users[0]).status_code == 429
    assert len(calls) == seen                                        # no retrieval paraphrases, no answer prompt


def test_limits_are_per_user(client, users, use_llm, limits):
    use_llm(make_fake_llm())
    limits(ask_per_minute=1)
    alice, bob = users

    assert ask(client, alice).status_code == 200
    assert ask(client, alice).status_code == 429
    assert ask(client, bob).status_code == 200                       # Bob's budget is his own


def test_ask_and_ask_stream_share_one_budget_and_a_streamed_rejection_is_a_real_429(client, users, use_llm, limits, db):
    use_llm(make_streaming_llm())
    limits(ask_per_minute=3)
    alice = users[0]

    assert ask(client, alice).status_code == 200
    assert ask(client, alice).status_code == 200
    assert ask(client, alice, "/ask/stream").status_code == 200       # the third, through the other endpoint

    streamed = ask(client, alice, "/ask/stream")
    assert streamed.status_code == 429
    assert streamed.headers["content-type"].startswith("application/json")      # an HTTP error, not an event stream
    assert "Retry-After" in streamed.headers
    assert ask(client, alice).status_code == 429
    assert db.query(Conversation).count() == 3 and db.query(Message).count() == 6


def test_the_daily_cap_blocks_even_when_the_burst_budget_is_fine(client, users, use_llm, limits):
    use_llm(make_fake_llm())
    limits(ask_per_minute=100, ask_per_day=2)

    assert [ask(client, users[0]).status_code for _ in range(2)] == [200, 200]
    resp = ask(client, users[0])

    assert resp.status_code == 429
    assert "Daily limit of 2 questions" in resp.json()["detail"] and "00:00 UTC" in resp.json()["detail"]
    assert 1 <= int(resp.headers["Retry-After"]) <= 86400


def test_a_request_denied_by_the_burst_limit_does_not_spend_daily_budget(client, users, use_llm, limits):
    use_llm(make_fake_llm())
    limits(ask_per_minute=2, ask_per_day=3)

    statuses = [ask(client, users[0]).status_code for _ in range(4)]
    assert statuses == [200, 200, 429, 429]

    today = f"{datetime.now(timezone.utc):%Y%m%d}"
    assert rate_limit._client().get(f"rl:ask:day:{users[0].id}:{today}") == "2"      # only the two answered questions


@pytest.mark.usefixtures("limits")
def test_an_unauthenticated_request_is_401_and_touches_no_counters(client):
    assert client.post("/ask", json={"query": QUESTION}).status_code == 401
    assert list(rate_limit._client().scan_iter("rl:*")) == []


def test_ask_still_works_when_redis_is_down(client, users, use_llm, limits, monkeypatch):
    use_llm(make_fake_llm())
    limits(ask_per_minute=1)

    def broken():
        raise redis.ConnectionError("redis is down")

    monkeypatch.setattr(rate_limit, "_scripts", broken)
    assert [ask(client, users[0]).status_code for _ in range(3)] == [200, 200, 200]      # unlimited, but alive


def test_limits_do_nothing_when_switched_off(client, users, use_llm, limits):
    use_llm(make_fake_llm())
    limits(ask_per_minute=1, rate_limit_enabled=False)

    assert [ask(client, users[0]).status_code for _ in range(4)] == [200] * 4
    assert list(rate_limit._client().scan_iter("rl:*")) == []


# --- uploads over HTTP ----------------------------------------------------------------------------------


@pytest.fixture
def no_dispatch(monkeypatch):
    """Uploads would hand the file to Celery; here that call does nothing."""
    from app.worker.celery_app import celery_app

    monkeypatch.setattr(celery_app, "send_task", lambda *_, **__: None)


def upload(client, user, number):
    return client.post("/documents", headers=headers_for(user),
                       files={"file": (f"doc{number}.pdf", f"%PDF upload {number}".encode(), PDF)})


@pytest.mark.usefixtures("no_dispatch")
def test_uploads_over_the_hourly_limit_are_429(client, users, limits):
    limits(upload_per_hour=2)

    assert [upload(client, users[0], n).status_code for n in range(2)] == [201, 201]
    resp = upload(client, users[0], 3)

    assert resp.status_code == 429
    assert "Too many uploads" in resp.json()["detail"]
    assert int(resp.headers["Retry-After"]) >= 1
    assert resp.headers["X-RateLimit-Limit"] == "2"


@pytest.mark.usefixtures("no_dispatch")
def test_upload_limit_is_per_user_and_separate_from_the_ask_budget(client, users, use_llm, limits):
    use_llm(make_fake_llm())
    limits(upload_per_hour=1, ask_per_minute=1)
    alice, bob = users

    assert upload(client, alice, 1).status_code == 201
    assert upload(client, alice, 2).status_code == 429
    assert upload(client, bob, 3).status_code == 201                  # per user
    assert ask(client, alice).status_code == 200                      # uploads and questions use different buckets


@pytest.mark.usefixtures("no_dispatch")
def test_reading_documents_is_not_limited(client, users, limits):
    limits(upload_per_hour=1, ask_per_minute=1)
    for _ in range(5):
        assert client.get("/documents", headers=headers_for(users[0])).status_code == 200
