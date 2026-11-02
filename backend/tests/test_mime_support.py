"""
MIME support alignment.

- UNIT: type resolution, factory/chunker coverage of every allowed type.
- INTEGRATION: real TXT/MD loading + cleaning + chunking; HTTP uploads through
  the documents router (real Postgres; send_task patched).
"""

import pytest

from app.ingestion.chunking.splitter import get_document_type
from app.ingestion.loaders.factory import SUPPORTED_MIME_TYPES, get_loader
from app.services.document import ALLOWED_MIME_TYPES, resolve_mime_type
from tests.test_loaders import make_csv, make_pptx, make_xlsx

MD = "text/markdown"
TXT = "text/plain"


def test_allowed_types_equal_supported_types():
    assert ALLOWED_MIME_TYPES == SUPPORTED_MIME_TYPES


@pytest.mark.parametrize("mime_type", sorted(SUPPORTED_MIME_TYPES))
def test_every_allowed_type_has_loader_and_chunking_strategy(mime_type):
    assert get_loader(mime_type) is not None
    assert get_document_type(mime_type) is not None


@pytest.mark.parametrize(
    "content_type,filename,expected",
    [
        ("application/pdf", "a.pdf", "application/pdf"),
        ("text/x-markdown", "a.md", MD),
        ("text/plain; charset=utf-8", "a.txt", TXT),
        ("application/octet-stream", "notes.MD", MD),
        (None, "sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("application/octet-stream", "noext", None),
        ("image/png", "a.png", "image/png"),
    ],
)
def test_resolve_mime_type(content_type, filename, expected):
    assert resolve_mime_type(content_type, filename) == expected


def test_text_and_markdown_load_clean_and_chunk():
    from app.ingestion.chunking.orchestrator import ChunkingOrchestrator
    from app.ingestion.cleaning.orchestrator import CleaningOrchestrator

    md = ("# Handbook\n\n## Vacation\n\nEmployees get twenty days of paid vacation.\n\n"
          "## Travel\n\nBook travel through the approved portal.\n").encode()
    for mime_type, data, name, file_type in [(MD, md, "h.md", "md"),
                                             (TXT, "Café policy: be kind.".encode("latin-1"), "c.txt", "txt")]:
        docs = get_loader(mime_type).load(data, name, {"document_id": "1"})
        assert docs[0].metadata["file_type"] == file_type and docs[0].metadata["source"] == name
        chunks = ChunkingOrchestrator().chunk_batch(CleaningOrchestrator().process_batch(docs), mime_type=mime_type)
        assert chunks and all(c.metadata["document_id"] == "1" for c in chunks)
    assert "Café" in get_loader(TXT).load("Café".encode("latin-1"), "c.txt")[0].page_content


# --- HTTP -------------------------------------------------------------------------


@pytest.fixture
def upload_client(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.db.database import get_db
    from app.db.models import User
    from app.dependencies.auth import get_current_user
    from app.routers.document import router
    from app.worker.celery_app import celery_app
    from tests.conftest import unique_clerk_id

    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: None)
    user = User(clerk_user_id=unique_clerk_id(), email="u@example.com")
    db.add(user)
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


@pytest.mark.parametrize(
    "name,data,content_type,stored_type",
    [
        ("staff.csv", make_csv(), "text/csv", "text/csv"),
        ("staff.xlsx", make_xlsx(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("deck.pptx", make_pptx(), "application/vnd.openxmlformats-officedocument.presentationml.presentation",
         "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("page.html", b"<h1>Hi</h1><p>There</p>", "text/html", "text/html"),
        ("notes.md", b"# Notes\n\nSome notes.", "application/octet-stream", MD),
        ("notes2.md", b"# Other\n\nMore notes.", "text/x-markdown", MD),
    ],
)
def test_http_upload_accepts_supported_types(upload_client, name, data, content_type, stored_type):
    resp = upload_client.post("/documents", files={"file": (name, data, content_type)})
    assert resp.status_code == 201, resp.text
    assert resp.json()["mime_type"] == stored_type


def test_http_upload_rejects_unsupported_type(upload_client):
    resp = upload_client.post("/documents", files={"file": ("a.png", b"\x89PNG....", "image/png")})
    assert resp.status_code == 400
