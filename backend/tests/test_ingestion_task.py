"""
ingest_file_task — MOCKED-PIPELINE task tests.

- `app.worker.task.ingest_file` is stubbed (no models, no Qdrant).
- Uses the REAL Postgres test DB for Document/DocumentBlob state.
- The task is executed in-process with `.apply()` (eager). NO Celery worker
  or broker is involved here.
"""

import hashlib

import pytest

from app.db.models import Document, DocumentBlob, User
from app.ingestion.model import IngestionResult
from tests.conftest import unique_clerk_id


@pytest.fixture
def task_module():
    """
    The registered ingest_file_task, with app.ingestion.pipeline stubbed if it
    hasn't been imported yet (so loading the task never builds embedding
    models or creates Qdrant collections).

    Celery returns the already-registered task when a module is re-imported,
    so tests patch `ingest_file` in the globals of the function Celery actually
    runs (`.globals`), not in whichever module object happens to be imported.
    """
    import importlib
    import sys
    import types

    if "app.worker.task" not in sys.modules and "app.ingestion.pipeline" not in sys.modules:
        stub = types.ModuleType("app.ingestion.pipeline")
        stub.ingest_file = lambda *a, **kw: None
        sys.modules["app.ingestion.pipeline"] = stub
    importlib.import_module("app.worker.task")
    from app.worker.celery_app import celery_app

    task = celery_app.tasks["ingest_file_task"]
    return types.SimpleNamespace(ingest_file_task=task, globals=task.run.__globals__)


def _stored_document(db, data=b"%PDF-1.4 stored bytes", filename="a.pdf", mime="application/pdf") -> int:
    user = User(clerk_user_id=unique_clerk_id(), email="u@example.com")
    db.add(user)
    db.commit()
    digest = hashlib.sha256(data).hexdigest()
    doc = Document(
        user_id=user.id, filename=filename, mime_type=mime, file_size=len(data),
        status="pending", document_hash=digest, storage_key=digest,
    )
    db.add(doc)
    db.flush()
    db.add(DocumentBlob(document_id=doc.id, data=data))
    db.commit()
    return doc.id


def _reload(db, doc_id) -> Document:
    db.expire_all()
    return db.get(Document, doc_id)


def _status_now(doc_id) -> str:
    """Read status in a separate session (what other clients would see)."""
    from app.db.database import SessionLocal

    s = SessionLocal()
    try:
        return s.get(Document, doc_id).status
    finally:
        s.close()


def test_success_transitions_pending_processing_ready(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    seen = {}

    def fake_ingest(data, filename, mime_type, metadata):
        seen.update(data=data, filename=filename, mime_type=mime_type, status=_status_now(doc_id))
        return IngestionResult(filename=filename, success=True, num_documents=1, num_chunks=3, point_ids=["p1"])

    monkeypatch.setitem(task_module.globals, "ingest_file", fake_ingest)
    assert _reload(db, doc_id).status == "pending"

    out = task_module.ingest_file_task.apply(args=[doc_id]).get()

    assert seen == {"data": b"%PDF-1.4 stored bytes", "filename": "a.pdf",
                    "mime_type": "application/pdf", "status": "processing"}
    doc = _reload(db, doc_id)
    assert doc.status == "ready" and doc.error_message is None
    assert out["status"] == "ready" and out["num_chunks"] == 3


def test_pipeline_failure_marks_failed_with_error(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    long_error = "nothing left after cleaning " + "x" * 2000
    monkeypatch.setitem(
        task_module.globals, "ingest_file",
        lambda *a: IngestionResult(filename="a.pdf", success=False, error=long_error),
    )

    out = task_module.ingest_file_task.apply(args=[doc_id]).get()

    doc = _reload(db, doc_id)
    assert doc.status == "failed"
    assert doc.error_message.startswith("nothing left after cleaning")
    assert len(doc.error_message) == 1000
    assert out["success"] is False


def _capture_retry(task_module, monkeypatch):
    from celery.exceptions import Retry

    retried = {}

    def fake_retry(exc=None, countdown=None, **kw):
        retried.update(exc=exc, countdown=countdown)
        return Retry(exc=exc)

    monkeypatch.setattr(task_module.ingest_file_task, "retry", fake_retry)
    return retried


def _boom(*a):
    raise ConnectionError("qdrant unreachable")


def test_transient_error_retries_with_backoff_and_pending_status(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    monkeypatch.setitem(task_module.globals, "ingest_file", _boom)
    retried = _capture_retry(task_module, monkeypatch)

    result = task_module.ingest_file_task.apply(args=[doc_id])

    assert result.state == "RETRY"
    assert isinstance(retried["exc"], ConnectionError)
    assert retried["countdown"] == 30
    doc = _reload(db, doc_id)
    assert doc.status == "pending"
    assert doc.error_message == "Retrying (attempt 1/4): ConnectionError: qdrant unreachable"


def test_retry_backoff_grows(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    monkeypatch.setitem(task_module.globals, "ingest_file", _boom)
    retried = _capture_retry(task_module, monkeypatch)
    task_module.ingest_file_task.apply(args=[doc_id], retries=2)
    assert retried["countdown"] == 120


def test_retries_exhausted_marks_failed(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    monkeypatch.setitem(task_module.globals, "ingest_file", _boom)
    retried = _capture_retry(task_module, monkeypatch)

    out = task_module.ingest_file_task.apply(args=[doc_id], retries=3).get()

    assert retried == {}
    assert out["status"] == "failed"
    doc = _reload(db, doc_id)
    assert doc.status == "failed"
    assert doc.error_message == "Failed after 4 attempts: ConnectionError: qdrant unreachable"


def test_permanent_failure_is_not_retried(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    monkeypatch.setitem(task_module.globals, "ingest_file",
                        lambda *a: IngestionResult(filename="a.pdf", success=False, error="Unsupported MIME type"))
    retried = _capture_retry(task_module, monkeypatch)
    task_module.ingest_file_task.apply(args=[doc_id]).get()
    assert retried == {}
    assert _reload(db, doc_id).status == "failed"


def test_missing_document_is_skipped(task_module, monkeypatch):
    called = []
    monkeypatch.setitem(task_module.globals, "ingest_file", lambda *a: called.append(a))
    out = task_module.ingest_file_task.apply(args=[987654]).get()
    assert out == {"document_id": 987654, "skipped": "not_found"}
    assert called == []


def test_rerun_after_failure_can_succeed(db, task_module, monkeypatch):
    """Failure state is recoverable: a later run clears the error and reaches ready."""
    doc_id = _stored_document(db)
    monkeypatch.setitem(task_module.globals, "ingest_file",
                        lambda *a: IngestionResult(filename="a.pdf", success=False, error="transient"))
    task_module.ingest_file_task.apply(args=[doc_id]).get()
    assert _reload(db, doc_id).status == "failed"

    monkeypatch.setitem(task_module.globals, "ingest_file",
                        lambda *a: IngestionResult(filename="a.pdf", success=True))
    task_module.ingest_file_task.apply(args=[doc_id]).get()
    doc = _reload(db, doc_id)
    assert doc.status == "ready" and doc.error_message is None


def test_task_passes_chunk_metadata_contract(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    captured = {}

    def fake_ingest(data, filename, mime_type, metadata):
        captured.update(metadata)
        return IngestionResult(filename=filename, success=True)

    monkeypatch.setitem(task_module.globals, "ingest_file", fake_ingest)
    task_module.ingest_file_task.apply(args=[doc_id]).get()

    doc = _reload(db, doc_id)
    assert captured["document_id"] == str(doc.id)
    assert captured["uploaded_by"] == str(doc.user_id)
    assert captured["doc_type"] == "pdf"
    assert captured["mime_type"] == "application/pdf"
    assert captured["source_name"] == "a.pdf"
    assert captured["document_hash"] == doc.document_hash
    assert captured["embedding_model"] == "BAAI/bge-large-en-v1.5"
    assert captured["created_at"].endswith("Z") and "T" in captured["created_at"]


# --- duplicate / interrupted execution (real Postgres advisory locks) ---------------


def _lock_held_elsewhere(doc_id):
    from contextlib import contextmanager

    from sqlalchemy import text

    from app.db.database import engine

    @contextmanager
    def held():
        conn = engine.connect()
        try:
            assert conn.execute(text("SELECT pg_try_advisory_lock(7301, :id)"), {"id": doc_id}).scalar()
            conn.commit()
            yield
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(7301, :id)"), {"id": doc_id})
            conn.commit()
            conn.close()

    return held()


def _lock_is_free(doc_id) -> bool:
    from sqlalchemy import text

    from app.db.database import engine

    with engine.connect() as conn:
        got = conn.execute(text("SELECT pg_try_advisory_lock(7301, :id)"), {"id": doc_id}).scalar()
        if got:
            conn.execute(text("SELECT pg_advisory_unlock(7301, :id)"), {"id": doc_id})
        conn.commit()
        return bool(got)


def test_concurrent_execution_is_skipped(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    called = []
    monkeypatch.setitem(task_module.globals, "ingest_file", lambda *a: called.append(a))

    with _lock_held_elsewhere(doc_id):
        out = task_module.ingest_file_task.apply(args=[doc_id]).get()

    assert out == {"document_id": doc_id, "skipped": "in_progress"}
    assert called == []
    assert _reload(db, doc_id).status == "pending"


def test_lock_released_after_success_and_failure(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    monkeypatch.setitem(task_module.globals, "ingest_file",
                        lambda *a: IngestionResult(filename="a.pdf", success=False, error="bad"))
    task_module.ingest_file_task.apply(args=[doc_id]).get()
    assert _lock_is_free(doc_id)

    monkeypatch.setitem(task_module.globals, "ingest_file", _boom)
    _capture_retry(task_module, monkeypatch)
    task_module.ingest_file_task.apply(args=[doc_id])
    assert _lock_is_free(doc_id)


def test_already_ready_document_is_not_reprocessed(db, task_module, monkeypatch):
    doc_id = _stored_document(db)
    calls = []

    def ok(*a):
        calls.append(1)
        return IngestionResult(filename="a.pdf", success=True)

    monkeypatch.setitem(task_module.globals, "ingest_file", ok)
    task_module.ingest_file_task.apply(args=[doc_id]).get()
    out = task_module.ingest_file_task.apply(args=[doc_id]).get()  # duplicate delivery
    assert out == {"document_id": doc_id, "skipped": "already_ready"}
    assert calls == [1]


def test_task_is_ack_late_and_requeued_on_worker_loss(task_module):
    t = task_module.ingest_file_task
    assert t.acks_late is True
    assert t.reject_on_worker_lost is True
