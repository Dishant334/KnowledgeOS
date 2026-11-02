"""Importing the pipeline must have no external side effects — INTEGRATION (real Qdrant check)."""

import importlib


def test_pipeline_import_does_not_touch_qdrant_or_load_models(monkeypatch):
    import sys

    from qdrant_client import QdrantClient

    # Other tests may have stubbed the module; import the real one fresh.
    monkeypatch.delitem(sys.modules, "app.ingestion.pipeline", raising=False)

    from app.core.config import settings
    from app.ingestion.embedding import embedders

    built = []
    monkeypatch.setattr(embedders, "TextEmbedding", lambda *a, **k: built.append("dense"))
    monkeypatch.setattr(embedders, "SparseTextEmbedding", lambda *a, **k: built.append("sparse"))

    before = {c.name for c in QdrantClient(url=settings.qdrant_url).get_collections().collections}
    pipeline = importlib.import_module("app.ingestion.pipeline")
    after = {c.name for c in QdrantClient(url=settings.qdrant_url).get_collections().collections}

    assert built == []
    assert after == before
    assert callable(pipeline.get_embedding_orchestrator)


def test_test_session_uses_isolated_collection():
    from app.ingestion.embedding.models import EmbeddingConfig

    assert EmbeddingConfig().collection_name == "knowledgeos_test_chunks"
