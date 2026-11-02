"""
Document loaders.

- UNIT: sync contract + factory coverage.
- INTEGRATION: real parsers (PyMuPDF, docx2txt, csv, BeautifulSoup, pandas/openpyxl,
  unstructured) on small files generated in-test. No mocks.
"""

import inspect
import io
import zipfile

import pytest
from langchain_core.documents import Document

from app.ingestion.loaders.factory import get_loader

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
CSV = "text/csv"
HTML = "text/html"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
ALL_MIME_TYPES = [PDF, DOCX, CSV, HTML, XLSX, PPTX]


# --- generated fixtures ---------------------------------------------------------


def make_pdf(pages=("Hello from page one of the PDF", "Second page text here")) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        doc.new_page().insert_text((72, 72), text)
    return doc.tobytes()


def make_docx(text="Hello from a DOCX paragraph") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


def make_csv() -> bytes:
    return b"name,role\nAlice,Engineer\nBob,Designer\n"


def make_html() -> bytes:
    return b"<html><body><h1>Policy</h1><p>Vacation is 20 days.</p><h2>Travel</h2><p>Book economy.</p></body></html>"


def make_xlsx() -> bytes:
    import pandas as pd

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame({"name": ["Alice", "Bob"], "role": ["Engineer", "Designer"]}).to_excel(w, index=False, sheet_name="Staff")
    return buf.getvalue()


def make_pptx() -> bytes:
    import pptx

    pres = pptx.Presentation()
    for title in ("Quarterly results", "Next steps"):
        slide = pres.slides.add_slide(pres.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = f"Details about {title.lower()}"
    buf = io.BytesIO()
    pres.save(buf)
    return buf.getvalue()


# --- unit -----------------------------------------------------------------------


@pytest.mark.parametrize("mime_type", ALL_MIME_TYPES)
def test_loader_is_synchronous(mime_type):
    loader = get_loader(mime_type)
    assert not inspect.iscoroutinefunction(loader.load), type(loader).__name__


def test_factory_rejects_unknown_mime_type():
    with pytest.raises(ValueError):
        get_loader("application/x-unknown")


# --- integration: real parsers -----------------------------------------------------


def _assert_docs(docs, file_type, filename):
    assert isinstance(docs, list) and docs
    for d in docs:
        assert isinstance(d, Document)
        assert d.page_content.strip()
        assert d.metadata["file_type"] == file_type
        assert d.metadata["filename"] == filename
        assert d.metadata["source"] == filename, "source must be the real filename, not a temp path"


def test_html_loader_real():
    docs = get_loader(HTML).load(make_html(), "policy.html", {"document_id": 1})
    _assert_docs(docs, "html", "policy.html")
    assert "Vacation is 20 days" in docs[0].page_content
    assert "<h1>" in docs[0].metadata["raw_html"]
    assert docs[0].metadata["document_id"] == 1


def test_xlsx_loader_real():
    docs = get_loader(XLSX).load(make_xlsx(), "staff.xlsx")
    _assert_docs(docs, "xlsx", "staff.xlsx")
    assert len(docs) == 2
    assert docs[0].metadata["sheet_name"] == "Staff"
    assert "name: Alice" in docs[0].page_content


def test_pptx_loader_real():
    docs = get_loader(PPTX).load(make_pptx(), "deck.pptx")
    _assert_docs(docs, "pptx", "deck.pptx")
    assert [d.metadata["slide_number"] for d in docs] == [1, 2]
    assert "Quarterly results" in docs[0].page_content


def test_pdf_loader_real():
    docs = get_loader(PDF).load(make_pdf(), "a.pdf")
    _assert_docs(docs, "pdf", "a.pdf")
    assert [d.metadata["page_number"] for d in docs] == [1, 2]
    assert all(d.metadata["total_pages"] == 2 for d in docs)
    assert "Hello from page one" in docs[0].page_content
    assert "Second page" in docs[1].page_content


def test_docx_loader_real():
    docs = get_loader(DOCX).load(make_docx(), "a.docx")
    _assert_docs(docs, "docx", "a.docx")
    assert "Hello from a DOCX paragraph" in docs[0].page_content


def test_csv_loader_real():
    docs = get_loader(CSV).load(make_csv(), "a.csv")
    _assert_docs(docs, "csv", "a.csv")
    assert len(docs) == 2
    assert "name: Alice" in docs[0].page_content
    assert [d.metadata["row_index"] for d in docs] == [0, 1]
