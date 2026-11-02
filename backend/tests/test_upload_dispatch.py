"""
Upload -> ingestion dispatch.

- MOCKED DISPATCH: celery_app.send_task patched; real Postgres test DB.
- REAL REDIS (no worker): message is actually published to the isolated
  Redis DB 15 queue and decoded.
"""

import asyncio
import base64
import io
import json

import pytest
from starlette.datastructures import Headers, UploadFile

from app.db.models import Document, User
from tests.conftest import unique_clerk_id

PDF = "application/pdf"


def _user(db) -> User:
    user = User(clerk_user_id=unique_clerk_id(), email="u@example.com")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _upload(db, user, data=b"%PDF dispatch", filename="a.pdf"):
    from app.services.document import create_document

    f = UploadFile(file=io.BytesIO(data), filename=filename, headers=Headers({"content-type": PDF}))
    return asyncio.run(create_document(db=db, user=user, file=f))


def _visible_in_new_session(doc_id) -> bool:
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        return s.get(Document, doc_id) is not None
    finally:
        s.close()


@pytest.fixture
def sent(monkeypatch):
    from app.worker.celery_app import celery_app

    calls = []

    def fake_send_task(name, args=None, **kw):
        calls.append({"name": name, "args": args, "committed": _visible_in_new_session(args[0]), **kw})

    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    return calls


# --- mocked dispatch ---------------------------------------------------------------


def test_new_upload_dispatches_once_after_commit(db, sent):
    doc = _upload(db, _user(db))
    assert len(sent) == 1
    assert sent[0]["name"] == "ingest_file_task"
    assert sent[0]["args"] == [doc.id]
    assert sent[0]["committed"] is True
    assert sent[0]["retry_policy"]["max_retries"] <= 3
    assert doc.status == "pending"


def test_dedup_reupload_does_not_dispatch(db, sent):
    user = _user(db)
    first = _upload(db, user)
    second = _upload(db, user, filename="again.pdf")
    assert first.id == second.id
    assert len(sent) == 1


def test_dispatch_failure_marks_document_failed(db, monkeypatch):
    from app.worker.celery_app import celery_app

    def broken(*a, **kw):
        raise ConnectionError("Error 61 connecting to localhost:6379")

    monkeypatch.setattr(celery_app, "send_task", broken)
    doc = _upload(db, _user(db))

    db.expire_all()
    stored = db.get(Document, doc.id)
    assert stored is not None and stored.blob.data == b"%PDF dispatch"
    assert stored.status == "failed"
    assert stored.error_message.startswith("Failed to queue ingestion: ConnectionError")


# --- real Redis (no worker) -----------------------------------------------------------


@pytest.fixture
def redis_queue():
    import redis

    from app.core.config import settings

    assert settings.redis_url.endswith("/15"), "tests must use the isolated Redis DB"
    r = redis.Redis.from_url(settings.redis_url)
    try:
        r.ping()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    r.delete("celery")
    yield r
    r.delete("celery")


def test_upload_publishes_real_message_to_redis(db, redis_queue):
    doc = _upload(db, _user(db), data=b"%PDF real redis")

    raw = redis_queue.lpop("celery")
    assert raw is not None, "no message published"
    message = json.loads(raw)
    assert message["headers"]["task"] == "ingest_file_task"
    body = json.loads(base64.b64decode(message["body"]))
    args = body[0]
    assert args == [doc.id]
    assert redis_queue.llen("celery") == 0
