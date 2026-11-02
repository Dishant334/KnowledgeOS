"""
Metadata propagation through REAL loader -> cleaning -> chunking stages
(no embedding, no Qdrant, no pipeline module import).
"""

import pytest

from app.ingestion.chunking.orchestrator import ChunkingOrchestrator
from app.ingestion.cleaning.orchestrator import CleaningOrchestrator
from app.ingestion.loaders.factory import get_loader
from tests.test_loaders import PDF, XLSX, make_pdf, make_xlsx

CONTRACT = {
    "document_id": "42",
    "uploaded_by": "7",
    "doc_type": "pdf",
    "mime_type": PDF,
    "source_name": "handbook.pdf",
    "document_hash": "a" * 64,
    "embedding_model": "BAAI/bge-large-en-v1.5",
    "created_at": "2026-11-03T10:00:00Z",
}


@pytest.mark.parametrize(
    "mime_type,data,filename",
    [
        (PDF, make_pdf(("Employee handbook covers vacation, travel and expenses in detail.",
                        "Travel must be booked through the approved portal at least two weeks ahead.")), "handbook.pdf"),
        (XLSX, make_xlsx(), "staff.xlsx"),
    ],
)
def test_every_chunk_carries_contract_metadata(mime_type, data, filename):
    docs = get_loader(mime_type).load(data, filename, dict(CONTRACT))
    cleaned = CleaningOrchestrator().process_batch(docs)
    chunks = ChunkingOrchestrator().chunk_batch(cleaned, mime_type=mime_type)

    assert chunks
    for i, chunk in enumerate(chunks):
        for key, value in CONTRACT.items():
            assert chunk.metadata[key] == value, (key, chunk.metadata.get(key))
        assert chunk.metadata["source"] == filename
        assert chunk.metadata["chunk_index"] == i
        assert chunk.metadata["total_chunks"] == len(chunks)
