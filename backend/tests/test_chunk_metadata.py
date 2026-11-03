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


def test_spreadsheet_chunks_never_mix_sheets():
    """20 rows per chunk, but a chunk must stay inside one sheet so its sheet name and row range are right."""
    import io

    import pandas as pd

    from tests.test_loaders import XLSX

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame({"name": [f"person{i}" for i in range(25)]}).to_excel(writer, index=False, sheet_name="Staff")
        pd.DataFrame({"item": [f"laptop{i}" for i in range(5)]}).to_excel(writer, index=False, sheet_name="Assets")

    docs = get_loader(XLSX).load(buffer.getvalue(), "company.xlsx")
    chunks = ChunkingOrchestrator().chunk_batch(CleaningOrchestrator().process_batch(docs), mime_type=XLSX)

    ranges = [(c.metadata["sheet_name"], c.metadata["row_start"], c.metadata["row_end"]) for c in chunks]
    assert ranges == [("Staff", 0, 19), ("Staff", 20, 24), ("Assets", 0, 4)]
    for c in chunks:
        sheet_text = "person" if c.metadata["sheet_name"] == "Staff" else "laptop"
        other_text = "laptop" if sheet_text == "person" else "person"
        assert sheet_text in c.page_content and other_text not in c.page_content


def test_csv_rows_still_form_normal_chunks():
    from tests.test_loaders import CSV

    rows = "\n".join(f"person{i},role{i}" for i in range(45))
    docs = get_loader(CSV).load(f"name,role\n{rows}\n".encode(), "staff.csv")
    chunks = ChunkingOrchestrator().chunk_batch(CleaningOrchestrator().process_batch(docs), mime_type=CSV)
    assert [(c.metadata["row_start"], c.metadata["row_end"]) for c in chunks] == [(0, 19), (20, 39), (40, 44)]
