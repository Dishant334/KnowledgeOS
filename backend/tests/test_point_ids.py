"""Deterministic Qdrant point IDs — UNIT tests (no Qdrant)."""

import uuid

from langchain_core.documents import Document

from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator

make_id = EmbeddingOrchestrator._make_id


def _chunk(**metadata):
    return Document(page_content="x", metadata=metadata)


def test_same_filename_different_documents_get_different_ids():
    a = _chunk(document_id="1", source="resume.pdf", page_number=1, chunk_index=0)
    b = _chunk(document_id="2", source="resume.pdf", page_number=1, chunk_index=0)
    assert make_id(a) != make_id(b)


def test_id_is_stable_and_valid_uuid():
    c = _chunk(document_id="5", source="a.pdf", chunk_index=3)
    assert make_id(c) == make_id(_chunk(document_id="5", source="renamed.pdf", chunk_index=3))
    uuid.UUID(make_id(c))


def test_distinct_chunks_of_one_document_are_unique():
    ids = {make_id(_chunk(document_id="9", chunk_index=i, page_number=i // 3 + 1)) for i in range(50)}
    assert len(ids) == 50


def test_fallback_without_document_id_is_unchanged():
    c = _chunk(source="a.pdf", page_number=2, chunk_index=1)
    assert make_id(c) == str(uuid.uuid5(uuid.NAMESPACE_URL, "a.pdf:2:1"))
