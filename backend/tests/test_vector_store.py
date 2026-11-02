"""
Qdrant collection setup — INTEGRATION tests against the real Qdrant container.

Each test uses a randomly named throwaway collection (deleted in teardown);
the application's `documents` collection is never touched.
"""

import logging
import uuid

import pytest
from qdrant_client.http.models import Distance, Modifier, SparseVectorParams, VectorParams

from app.ingestion.embedding.models import EmbeddingConfig
from app.ingestion.embedding.vector_store import DENSE_DIM, ensure_collection, get_qdrant_client, payload_key


@pytest.fixture
def qdrant_config():
    config = EmbeddingConfig(collection_name=f"test_{uuid.uuid4().hex[:12]}")
    client = get_qdrant_client(config)
    try:
        client.get_collections()
    except Exception as exc:
        pytest.skip(f"Qdrant unavailable: {exc}")
    yield client, config
    if client.collection_exists(config.collection_name):
        client.delete_collection(config.collection_name)


def test_creates_hybrid_collection_with_bm25_idf(qdrant_config):
    client, config = qdrant_config
    ensure_collection(client, config)

    params = client.get_collection(config.collection_name).config.params
    dense = params.vectors["dense"]
    assert dense.size == DENSE_DIM
    assert dense.distance == Distance.COSINE
    assert params.sparse_vectors["sparse"].modifier == Modifier.IDF


def test_creates_payload_indexes(qdrant_config):
    client, config = qdrant_config
    ensure_collection(client, config)
    schema = client.get_collection(config.collection_name).payload_schema
    assert {payload_key(f) for f in config.indexed_payload_fields} <= set(schema)


def test_ensure_collection_is_idempotent(qdrant_config):
    client, config = qdrant_config
    ensure_collection(client, config)
    ensure_collection(client, config)
    info = client.get_collection(config.collection_name)
    assert info.config.params.sparse_vectors["sparse"].modifier == Modifier.IDF
    assert {payload_key(f) for f in config.indexed_payload_fields} <= set(info.payload_schema)


def test_existing_collection_without_idf_is_warned_not_modified(qdrant_config, caplog, monkeypatch):
    client, config = qdrant_config
    # Alembic's fileConfig (run by other tests) disables pre-existing loggers.
    monkeypatch.setattr(logging.getLogger("app.ingestion.embedding.vector_store"), "disabled", False)
    client.create_collection(
        collection_name=config.collection_name,
        vectors_config={"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
        sparse_vectors_config={"sparse": SparseVectorParams()},
    )

    with caplog.at_level(logging.WARNING, logger="app.ingestion.embedding.vector_store"):
        ensure_collection(client, config)

    assert any("lacks modifier=IDF" in r.message for r in caplog.records)
    sparse = client.get_collection(config.collection_name).config.params.sparse_vectors["sparse"]
    assert sparse.modifier != Modifier.IDF  # untouched


# --- Filters against real points written by QdrantVectorStore ----------------------


from langchain_core.embeddings import Embeddings  # noqa: E402
from langchain_qdrant import SparseEmbeddings  # noqa: E402


class _FakeDense(Embeddings):
    """Tiny deterministic dense embedder (DENSE_DIM) — avoids loading the real model."""

    def _vec(self, text):
        import hashlib

        h = hashlib.sha256(text.encode()).digest()
        v = [h[i % len(h)] / 255.0 + 0.01 for i in range(DENSE_DIM)]
        n = sum(x * x for x in v) ** 0.5
        return [x / n for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class _FakeSparse(SparseEmbeddings):
    def embed_documents(self, texts):
        from langchain_qdrant.sparse_embeddings import SparseVector

        return [SparseVector(indices=[abs(hash(w)) % 10_000 for w in set(t.split())] or [0],
                             values=[1.0] * (len(set(t.split())) or 1)) for t in texts]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


def test_filters_match_metadata_written_by_vector_store(qdrant_config):
    from langchain_core.documents import Document
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    from app.retrieval.filters import build_qdrant_filter

    client, config = qdrant_config
    ensure_collection(client, config)
    store = QdrantVectorStore(
        client=client, collection_name=config.collection_name,
        embedding=_FakeDense(), sparse_embedding=_FakeSparse(),
        retrieval_mode=RetrievalMode.HYBRID, vector_name="dense", sparse_vector_name="sparse",
    )
    rows = [
        ("vacation policy", {"document_id": "1", "uploaded_by": "10", "doc_type": "pdf", "created_at": "2026-01-10T00:00:00Z"}),
        ("travel policy", {"document_id": "2", "uploaded_by": "10", "doc_type": "docx", "created_at": "2026-06-10T00:00:00Z"}),
        ("expense policy", {"document_id": "3", "uploaded_by": "20", "doc_type": "pdf", "created_at": "2026-09-10T00:00:00Z"}),
    ]
    store.add_documents([Document(page_content=t, metadata=m) for t, m in rows])

    def ids(flt):
        points, _ = client.scroll(config.collection_name, scroll_filter=flt, limit=10, with_payload=True)
        return sorted(p.payload["metadata"]["document_id"] for p in points)

    assert ids(build_qdrant_filter(doc_type="pdf")) == ["1", "3"]
    assert ids(build_qdrant_filter(uploaded_by="10")) == ["1", "2"]
    assert ids(build_qdrant_filter(uploaded_by="10", doc_type="pdf")) == ["1"]
    assert ids(build_qdrant_filter(created_after="2026-05-01T00:00:00Z")) == ["2", "3"]
    assert ids(build_qdrant_filter(uploaded_by="999")) == []

    # And through the vector store's own hybrid search path:
    hits = store.similarity_search("policy", k=10, filter=build_qdrant_filter(uploaded_by="20"))
    assert [d.metadata["document_id"] for d in hits] == ["3"]
