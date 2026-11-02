"""
Vector lifecycle — INTEGRATION tests against REAL Qdrant (isolated test
collection) and REAL Postgres. Embedding models are replaced by small fake
embedders (no 1.2 GB model load); everything else is real.
"""

import hashlib
import io

import pytest
from langchain_core.documents import Document as LCDocument

from app.db.models import Document, DocumentBlob, User
from app.ingestion.embedding import vector_store as vs
from app.ingestion.embedding.models import EmbeddingConfig
from tests.conftest import unique_clerk_id
from tests.test_vector_store import _FakeDense, _FakeSparse

PDF = "application/pdf"


@pytest.fixture
def qdrant(monkeypatch):
    """Fresh isolated test collection + fake embedders for any vector store built."""
    config = EmbeddingConfig()
    assert config.collection_name == "knowledgeos_test_chunks"
    client = vs.get_qdrant_client(config)
    try:
        client.get_collections()
    except Exception as exc:
        pytest.skip(f"Qdrant unavailable: {exc}")
    if client.collection_exists(config.collection_name):
        client.delete_collection(config.collection_name)
    monkeypatch.setattr(vs, "build_dense_embedder", lambda cfg: _FakeDense())
    monkeypatch.setattr(vs, "build_sparse_embedder", lambda cfg: _FakeSparse())
    yield client, config
    if client.collection_exists(config.collection_name):
        client.delete_collection(config.collection_name)


def _orchestrator():
    from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator

    return EmbeddingOrchestrator()


def _chunks(document_id: str, n: int, text="policy text"):
    return [
        LCDocument(page_content=f"{text} {i}", metadata={"document_id": document_id, "chunk_index": i, "source": "a.pdf"})
        for i in range(n)
    ]


def _count(client, config, document_id=None):
    flt = vs.document_points_filter(document_id) if document_id is not None else None
    return client.count(config.collection_name, count_filter=flt, exact=True).count


def test_delete_document_points_removes_only_that_document(qdrant):
    client, config = qdrant
    orch = _orchestrator()
    orch.embed_and_index(_chunks("1", 3))
    orch.embed_and_index(_chunks("2", 4))

    vs.delete_document_points("1")

    assert _count(client, config, "1") == 0
    assert _count(client, config, "2") == 4


def test_delete_is_noop_when_collection_missing(qdrant):
    client, config = qdrant
    assert not client.collection_exists(config.collection_name)
    vs.delete_document_points("123")  # must not raise


def test_reindex_replaces_stale_chunks(qdrant):
    client, config = qdrant
    orch = _orchestrator()
    orch.embed_and_index(_chunks("7", 5))
    assert _count(client, config, "7") == 5
    orch.embed_and_index(_chunks("7", 2, text="revised"))  # e.g. re-run after interruption
    assert _count(client, config, "7") == 2


def test_reindex_same_chunks_is_idempotent(qdrant):
    client, config = qdrant
    orch = _orchestrator()
    ids1 = orch.embed_and_index(_chunks("8", 3))
    ids2 = orch.embed_and_index(_chunks("8", 3))
    assert ids1 == ids2
    assert _count(client, config, "8") == 3


# --- HTTP delete through the documents router ------------------------------------


def _stored(db, data=b"%PDF del"):
    user = User(clerk_user_id=unique_clerk_id(), email="u@example.com")
    db.add(user)
    db.commit()
    digest = hashlib.sha256(data).hexdigest()
    doc = Document(user_id=user.id, filename="a.pdf", mime_type=PDF, file_size=len(data),
                   status="ready", document_hash=digest, storage_key=digest)
    db.add(doc)
    db.flush()
    db.add(DocumentBlob(document_id=doc.id, data=data))
    db.commit()
    return user, doc.id


@pytest.fixture
def client_for(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.db.database import get_db
    from app.dependencies.auth import get_current_user
    from app.routers.document import router

    def make(user):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    return make


def test_http_delete_removes_vectors(db, qdrant, client_for):
    client, config = qdrant
    user, doc_id = _stored(db)
    _orchestrator().embed_and_index(_chunks(str(doc_id), 3))
    _orchestrator().embed_and_index(_chunks("other", 2))

    resp = client_for(user).delete(f"/documents/{doc_id}")

    assert resp.status_code == 204
    assert _count(client, config, str(doc_id)) == 0
    assert _count(client, config, "other") == 2
    assert db.get(Document, doc_id) is None


def test_http_delete_keeps_document_when_qdrant_unavailable(db, qdrant, client_for, monkeypatch):
    import app.services.document as svc

    user, doc_id = _stored(db)

    def down(*a, **kw):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(svc, "delete_document_points", down)
    resp = client_for(user).delete(f"/documents/{doc_id}")

    assert resp.status_code == 503
    db.expire_all()
    assert db.get(Document, doc_id) is not None


# --- deleted while ingesting ------------------------------------------------------------


def test_document_deleted_during_ingestion_leaves_no_vectors(db, qdrant):

    import importlib
    import sys
    import types

    if "app.worker.task" not in sys.modules and "app.ingestion.pipeline" not in sys.modules:
        stub = types.ModuleType("app.ingestion.pipeline")
        stub.ingest_file = lambda *a, **kw: None
        sys.modules["app.ingestion.pipeline"] = stub
    importlib.import_module("app.worker.task")
    from app.ingestion.model import IngestionResult
    from app.worker.celery_app import celery_app

    task = celery_app.tasks["ingest_file_task"]
    client, config = qdrant
    _, doc_id = _stored(db)
    db.get(Document, doc_id).status = "pending"
    db.commit()

    def index_then_user_deletes(data, filename, mime_type, metadata):
        _orchestrator().embed_and_index(_chunks(metadata["document_id"], 3))
        from sqlalchemy import text

        from app.db.database import engine

        with engine.begin() as conn:  # the user deletes the document mid-ingestion
            conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": doc_id})
        return IngestionResult(filename=filename, success=True, num_chunks=3)

    original = task.run.__globals__["ingest_file"]
    task.run.__globals__["ingest_file"] = index_then_user_deletes
    try:
        out = task.apply(args=[doc_id]).get()
    finally:
        task.run.__globals__["ingest_file"] = original

    assert out == {"document_id": doc_id, "skipped": "deleted_during_ingestion"}
    assert _count(client, config, str(doc_id)) == 0
