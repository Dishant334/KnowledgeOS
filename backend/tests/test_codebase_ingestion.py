# CODEBASE-FEATURE (Stage 2): single code file, end to end.
#
# UNIT (no services): MIME resolution, CodeLoader, CodeChunkingStrategy, the
#   friendly failure reasons, the doc_type tag.
# MOCKED: the cleaner bypass test runs the REAL ingest_file pipeline but swaps
#   the embedder for a fake that records the chunks (no models, no Qdrant).
# HTTP: uploads through the documents router (real Postgres, send_task patched).
# INTEGRATION: a REAL Celery worker + real models + real Qdrant test collection
#   (reuses the fixtures of test_worker_e2e.py).
import types

import pytest
from langchain_core.documents import Document

from app.ingestion.chunking.model import ChunkingConfig, DocumentType
from app.ingestion.chunking.orchestrator import ChunkingOrchestrator
from app.ingestion.chunking.splitter import get_document_type
from app.ingestion.loaders.code_loader import CodeLoader
from app.ingestion.loaders.factory import SUPPORTED_MIME_TYPES, get_loader
from app.schemas.document import friendly_failure_reason
from app.services.document import ALLOWED_MIME_TYPES, CODE_MIME_TYPE, resolve_mime_type

# Fixtures/helpers of the real-worker tests, reused for the integration tests below.
from tests.test_worker_e2e import (  # noqa: F401
    _clear_test_collection_points,
    _error_message,
    _points,
    _upload,
    _wait,
    qdrant,
    user_headers,
    worker,
)

PY_SOURCE = '''import os


def read_config(path):
    """Return the config text, or None when the file is missing."""
    if not os.path.exists(path):
        return None
    with open(path) as handle:
        return handle.read()


class Cache:
    def __init__(self):
        self.items = {}

    def get(self, key):
        if key in self.items:
            return self.items[key]
        return None

    def put(self, key, value):
        self.items[key] = value
        return None
'''


# --- the stored type ----------------------------------------------------------------


def test_code_type_is_allowed_and_has_loader_and_strategy():
    assert CODE_MIME_TYPE == "text/x-code"
    assert CODE_MIME_TYPE in ALLOWED_MIME_TYPES and CODE_MIME_TYPE in SUPPORTED_MIME_TYPES
    assert isinstance(get_loader(CODE_MIME_TYPE), CodeLoader)
    assert get_document_type(CODE_MIME_TYPE) == DocumentType.CODE


@pytest.mark.parametrize(
    "content_type,filename",
    [
        ("application/octet-stream", "main.py"),
        ("text/x-python", "main.py"),
        ("text/plain", "main.py"),          # browsers often send text/plain for code
        (None, "main.py"),
        ("text/javascript", "app.js"),
        ("video/mp2t", "app.ts"),            # the classic browser mistake for .ts
        ("application/octet-stream", "Widget.tsx"),
        ("text/x-java-source", "Main.java"),
        ("text/x-csrc", "util.c"),
        ("text/x-chdr", "util.h"),
        ("text/x-c++src", "util.cpp"),
        ("application/octet-stream", "util.cc"),
        ("application/octet-stream", "SRC.PY"),   # case-insensitive
    ],
)
def test_code_extensions_resolve_to_the_code_type_whatever_the_client_says(content_type, filename):
    assert resolve_mime_type(content_type, filename) == CODE_MIME_TYPE


@pytest.mark.parametrize(
    "content_type,filename,expected",
    [
        ("application/pdf", "a.pdf", "application/pdf"),
        ("text/plain", "notes.txt", "text/plain"),
        ("application/octet-stream", "notes.md", "text/markdown"),
        ("text/csv", "data.csv", "text/csv"),
        ("text/html", "page.html", "text/html"),
        ("application/octet-stream", "noext", None),
        ("image/png", "a.png", "image/png"),
    ],
)
def test_non_code_files_resolve_exactly_as_before(content_type, filename, expected):
    assert resolve_mime_type(content_type, filename) == expected


# --- CodeLoader ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,language",
    [("a.py", "python"), ("src/a.js", "javascript"), ("a.jsx", "javascript"), ("a.ts", "typescript"),
     ("A.java", "java"), ("a.c", "c"), ("a.h", "c"), ("a.cpp", "cpp"), ("a.hpp", "cpp")],
)
def test_loader_sets_language_file_path_and_keeps_metadata(filename, language):
    [doc] = CodeLoader().load(b"x = 1\n", filename, {"document_id": "7"})
    assert doc.metadata["language"] == language
    assert doc.metadata["file_path"] == filename
    assert doc.metadata["filename"] == doc.metadata["source"] == filename
    assert doc.metadata["file_type"] == "code"
    assert doc.metadata["document_id"] == "7"


def test_loader_keeps_the_text_byte_for_byte():
    source = "def f():\n\tif x:\r\n        return 1  \n\n\n    \nreturn 2\n"
    [doc] = CodeLoader().load(source.encode(), "a.py")
    assert doc.page_content == source  # tabs, CRLF, trailing spaces, blank lines, final newline


def test_loader_drops_a_utf8_bom_but_nothing_else():
    [doc] = CodeLoader().load(b"\xef\xbb\xbfprint('hi')\n", "a.py")
    assert doc.page_content == "print('hi')\n"


def test_loader_refuses_non_utf8_instead_of_guessing():
    with pytest.raises(ValueError, match="not valid UTF-8"):
        CodeLoader().load("caf\xe9 = 1\n".encode("latin-1"), "a.py")


@pytest.mark.parametrize("data", [b"", b"   \n\t\n"])
def test_loader_refuses_an_empty_file(data):
    with pytest.raises(ValueError, match="Code file is empty"):
        CodeLoader().load(data, "a.py")


def test_loader_refuses_an_unknown_extension():
    with pytest.raises(ValueError, match="Unsupported code file"):
        CodeLoader().load(b"data", "notes.xyz")


# --- chunking -----------------------------------------------------------------------


def _chunk(source: str, filename: str, **config) -> list[Document]:
    docs = CodeLoader().load(source.encode(), filename, {"document_id": "1"})
    return ChunkingOrchestrator(ChunkingConfig(**config)).chunk_batch(docs, mime_type=CODE_MIME_TYPE)


def test_a_small_file_is_one_chunk_equal_to_the_source():
    [chunk] = _chunk(PY_SOURCE, "mod.py")
    # Stage 6: the AST chunker trims trailing whitespace of a chunk (a final newline); every line and all indentation stay
    assert chunk.page_content == PY_SOURCE.rstrip()
    assert chunk.metadata["language"] == "python" and chunk.metadata["file_path"] == "mod.py"
    assert chunk.metadata["chunk_index"] == 0 and chunk.metadata["total_chunks"] == 1


def test_a_big_file_is_split_and_every_chunk_keeps_its_indentation():
    big = PY_SOURCE * 12
    chunks = _chunk(big, "mod.py", chunk_size=120, chunk_overlap=0)
    assert len(chunks) > 3
    original_lines = set(big.split("\n"))
    for chunk in chunks:
        assert chunk.metadata["language"] == "python"
        for line in chunk.page_content.split("\n"):
            # a stripped first line (lost indentation) would not be found in the original
            assert line in original_lines, repr(line)
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize(
    "filename,source",
    [
        ("app.js", "function add(a, b) {\n  return a + b;\n}\n\nconst mul = (a, b) => {\n  return a * b;\n};\n" * 30),
        ("Main.java", "public class Main {\n    public static void main(String[] args) {\n        System.out.println(1);\n    }\n}\n" * 30),
        ("util.c", "int add(int a, int b) {\n    return a + b;\n}\n\nint main(void) {\n    return 0;\n}\n" * 30),
        ("util.cpp", "int add(int a, int b) {\n    return a + b;\n}\n\nclass A {\npublic:\n    int f() { return 1; }\n};\n" * 30),
        ("x.ts", "export function add(a: number, b: number): number {\n  return a + b;\n}\n" * 30),
    ],
)
def test_every_tier1_language_chunks_without_losing_a_line(filename, source):
    chunks = _chunk(source, filename, chunk_size=100, chunk_overlap=0)
    assert len(chunks) > 1
    original_lines = set(source.split("\n"))
    assert all(line in original_lines for c in chunks for line in c.page_content.split("\n"))


def test_chunks_stay_within_the_token_budget():
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    chunks = _chunk(PY_SOURCE * 20, "mod.py", chunk_size=128, chunk_overlap=16)
    assert max(len(encoding.encode(c.page_content)) for c in chunks) <= 128


# --- the cleaner is bypassed (A1) ----------------------------------------------------


@pytest.fixture
def recorded_chunks(monkeypatch):
    """The REAL ingest_file pipeline, with the embedder replaced by a recorder."""
    from app.ingestion import pipeline

    captured: list[Document] = []

    class FakeEmbedder:
        def embed_and_index(self, chunks):
            captured.extend(chunks)
            return [f"p{i}" for i in range(len(chunks))]

    monkeypatch.setattr(pipeline, "get_embedding_orchestrator", lambda: FakeEmbedder())
    return captured


def test_pipeline_keeps_code_byte_for_byte_and_does_not_clean_it(recorded_chunks):
    from app.ingestion.pipeline import ingest_file

    # The cleaner removes repeated lines and flattens whitespace; code must survive both.
    source = "def f(x):\n    if x:\n        return None\n    if not x:\n        return None\n    return None\n"
    result = ingest_file(source.encode(), "f.py", CODE_MIME_TYPE, {"document_id": "1"})
    assert result.success, result.error
    assert [c.page_content for c in recorded_chunks] == [source.rstrip()]       # (a final newline is trimmed; nothing else)
    assert recorded_chunks[0].page_content.count("return None") == 3


def test_pipeline_keeps_repeated_closing_braces_in_c(recorded_chunks):
    from app.ingestion.pipeline import ingest_file

    source = "int f(int x) {\n    if (x) {\n        if (x > 1) {\n            return 1;\n        }\n    }\n    return 0;\n}\n"
    result = ingest_file(source.encode(), "f.c", CODE_MIME_TYPE, {"document_id": "1"})
    assert result.success, result.error
    text = "".join(c.page_content for c in recorded_chunks)
    assert text == source.rstrip() and text.count("}") == 3


def test_pipeline_reports_an_empty_code_file_as_failed(recorded_chunks):
    from app.ingestion.pipeline import ingest_file

    result = ingest_file(b"\n\n", "empty.py", CODE_MIME_TYPE, {"document_id": "1"})
    assert result.success is False and "Code file is empty" in result.error
    assert recorded_chunks == []


def test_docs_still_go_through_the_cleaner(recorded_chunks):
    from app.ingestion.pipeline import ingest_file

    body = "Employees receive twenty days of paid vacation per year under the leave policy.\n\n" * 3
    result = ingest_file(body.encode(), "p.txt", "text/plain", {"document_id": "1"})
    assert result.success, result.error
    assert recorded_chunks  # prose still passes through cleaning and chunking as before


# --- friendly failure reasons (S11) ----------------------------------------------------


def test_failure_reasons_for_code_are_friendly_and_leak_nothing():
    not_utf8 = friendly_failure_reason("failed", "Source file is not valid UTF-8 text: 'utf-8' codec can't decode byte")
    empty = friendly_failure_reason("failed", "Code file is empty")
    assert "UTF-8" in not_utf8 and "codec" not in not_utf8
    assert "empty" in empty.lower()
    assert friendly_failure_reason("ready", "Code file is empty") is None


# --- doc_type tag --------------------------------------------------------------------------


def test_code_chunks_are_tagged_doc_type_code():
    from datetime import datetime

    from app.worker.task import build_chunk_metadata

    document = types.SimpleNamespace(
        id=5, user_id=2, mime_type=CODE_MIME_TYPE, filename="main.py", document_hash="h",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
    )
    meta = build_chunk_metadata(document)
    assert meta["doc_type"] == "code" and meta["mime_type"] == CODE_MIME_TYPE and meta["source_name"] == "main.py"


# --- HTTP upload ----------------------------------------------------------------------------


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
    "name,content_type",
    [("main.py", "application/octet-stream"), ("app.js", "text/javascript"), ("app.ts", "video/mp2t"),
     ("Main.java", "text/x-java-source"), ("util.c", "text/plain"), ("util.cpp", "")],
)
def test_http_upload_accepts_code_files_and_stores_the_code_type(upload_client, name, content_type):
    resp = upload_client.post("/documents", files={"file": (name, f"// {name}\nint x;\n".encode(), content_type)})
    assert resp.status_code == 201, resp.text
    assert resp.json()["mime_type"] == CODE_MIME_TYPE


@pytest.mark.parametrize("name", ["credentials.py", "id_rsa.py", "credentials_helper.js"])
def test_http_upload_refuses_secret_looking_code_files(upload_client, name):
    resp = upload_client.post("/documents", files={"file": (name, b"TOKEN = 'abc'\n", "text/plain")})
    assert resp.status_code == 400
    assert "secret" in resp.json()["detail"].lower()


def test_http_upload_refuses_minified_files(upload_client):
    resp = upload_client.post("/documents", files={"file": ("app.min.js", b"var a=1;", "text/javascript")})
    assert resp.status_code == 400
    assert "minified" in resp.json()["detail"].lower() or "generated" in resp.json()["detail"].lower()


def test_secret_name_rule_does_not_touch_docs_uploads(upload_client):
    resp = upload_client.post("/documents", files={"file": ("credentials.txt", b"How to get credentials.", "text/plain")})
    assert resp.status_code == 201
    assert resp.json()["mime_type"] == "text/plain"


# --- INTEGRATION: real worker, real models, real Qdrant --------------------------------------


def test_python_file_reaches_ready_and_is_retrievable(client, worker, qdrant, user_headers):
    from app.ingestion.embedding.models import EmbeddingConfig
    from app.ingestion.embedding.vector_store import get_vector_store
    from app.retrieval.filters import build_qdrant_filter

    doc = _upload(client, user_headers, "config_cache.py", PY_SOURCE.encode(), "application/octet-stream")
    assert doc["mime_type"] == CODE_MIME_TYPE and doc["status"] == "pending"

    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready", _error_message(doc["id"])

    points = _points(qdrant, doc["id"])
    assert points
    for p in points:
        meta = p.payload["metadata"]
        assert meta["doc_type"] == "code" and meta["language"] == "python"
        assert meta["file_path"] == meta["source_name"] == "config_cache.py"
    # A small file is one chunk and arrives in Qdrant exactly as uploaded.
    assert [p.payload["page_content"] for p in points] == [PY_SOURCE.rstrip()]

    uploaded_by = points[0].payload["metadata"]["uploaded_by"]
    store = get_vector_store(EmbeddingConfig())
    hits = store.similarity_search("where is read_config defined?", k=3,
                                   filter=build_qdrant_filter(uploaded_by=uploaded_by))
    assert hits and "def read_config" in hits[0].page_content
    assert store.similarity_search("read_config", k=3, filter=build_qdrant_filter(uploaded_by="nobody")) == []
