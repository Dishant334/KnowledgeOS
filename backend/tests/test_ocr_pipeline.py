"""
OCR stage of the pipeline.

- INTEGRATION (real Tesseract + PyMuPDF): scanned (image-only) page is OCR'd.
- PARTIALLY MOCKED: one page's OCR forced to fail; other pages must survive.
"""

import pytest
from langchain_core.documents import Document


def make_scanned_pdf(text="Scanned invoice total amount due") -> bytes:
    """A PDF whose only page is an IMAGE of text (no extractable text layer)."""
    import pymupdf

    src = pymupdf.open()
    page = src.new_page()
    page.insert_text((72, 120), text, fontsize=28)
    png = page.get_pixmap(dpi=200).tobytes("png")

    out = pymupdf.open()
    out.new_page().insert_image(pymupdf.Rect(0, 0, 595, 842), stream=png)
    return out.tobytes()


@pytest.fixture
def pipeline(monkeypatch):
    import importlib
    import sys

    monkeypatch.delitem(sys.modules, "app.ingestion.pipeline", raising=False)
    return importlib.import_module("app.ingestion.pipeline")


def test_scanned_page_is_ocred_with_real_tesseract(pipeline):
    import shutil

    if not shutil.which("tesseract"):
        pytest.skip("tesseract binary not installed")
    pdf = make_scanned_pdf()
    docs = pipeline.get_loader("application/pdf").load(pdf, "scan.pdf")
    assert not docs[0].page_content.strip()  # nothing extractable without OCR

    out, warnings = pipeline.run_ocr_on_pages(docs, pdf)
    assert out[0].metadata["ocr_used"] is True
    assert "invoice" in out[0].page_content.lower()
    assert out[0].metadata["ocr_confidence"] > 0


def test_one_failing_ocr_page_does_not_fail_document(pipeline, monkeypatch):
    from app.ingestion.ocr.orchestrator import OCRResult, OCRStageError

    def fake_process_page(pdf_data, page_number, extracted_text=""):
        if page_number == 2:
            raise OCRStageError("ocr_extract[default]", RuntimeError("Tesseract OCR failed"))
        return OCRResult(text=extracted_text, used_ocr=False)

    monkeypatch.setattr(pipeline.ocr_orchestrator, "process_page", fake_process_page)
    docs = [
        Document(page_content=f"Page {i} has enough real words to skip OCR.", metadata={"page_number": i})
        for i in (1, 2, 3)
    ]

    out, warnings = pipeline.run_ocr_on_pages(docs, b"%PDF-unused")

    assert [d.metadata["page_number"] for d in out] == [1, 2, 3]
    assert out[1].metadata["ocr_failed"] is True
    assert out[1].page_content == docs[1].page_content
    assert len(warnings) == 1 and warnings[0].startswith("page_2: ocr_failed:")


# --- error classification in ingest_file (embedding stage stubbed) -----------------


def test_transient_error_propagates_from_ingest_file(pipeline, monkeypatch):
    from tests.test_loaders import PDF, make_pdf

    class _Down:
        def embed_and_index(self, chunks):
            raise ConnectionError("qdrant down")

    monkeypatch.setattr(pipeline, "get_embedding_orchestrator", lambda: _Down())
    with pytest.raises(ConnectionError):
        pipeline.ingest_file(make_pdf(), "a.pdf", PDF)


def test_content_error_is_reported_not_raised(pipeline):
    result = pipeline.ingest_file(b"whatever", "a.bin", "application/x-unknown")
    assert result.success is False
    assert "Unsupported MIME type" in result.error
