# CODEBASE-FEATURE (Stage 9): project zip ingestion.
#
# UNIT (no services): ZipLoader on hand-built hostile and normal zips, ProjectChunkingStrategy.
# MOCKED: the REAL ingest_file pipeline with the embedder replaced by a recorder.
# HTTP: uploads through the documents router (real Postgres, send_task patched): the chat mode rules (S12).
# INTEGRATION: a REAL Celery worker + real models + real Qdrant test collection (fixtures of test_worker_e2e.py).
import io
import json
import stat
import struct
import zipfile

import pytest
from langchain_core.documents import Document

from app.ingestion.chunking.model import ChunkingConfig
from app.ingestion.chunking.orchestrator import ChunkingOrchestrator
from app.ingestion.codebase import policy
from app.ingestion.loaders.factory import SUPPORTED_MIME_TYPES, get_loader
from app.ingestion.loaders.zip_loader import ZIP_MIME_TYPE, ZipLoader
from app.schemas.document import friendly_failure_reason

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

PY = b'import os\n\n\ndef read_config(path):\n    """Return the config text."""\n    return open(path).read()\n'


# ---------------------------------------------------------------- helpers

def make_zip(entries, compression=zipfile.ZIP_DEFLATED) -> bytes:
    """entries: list of (name, bytes) or (ZipInfo, bytes). Names are kept exactly as given (no sanitising)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as zf:
        for name, data in entries:
            if isinstance(name, zipfile.ZipInfo):
                zf.writestr(name, data)
            else:
                info = zipfile.ZipInfo(name)
                info.compress_type = compression
                zf.writestr(info, data)
    return buffer.getvalue()


def load(entries):
    return ZipLoader().load_with_summary(make_zip(entries) if isinstance(entries, list) else entries, "proj.zip", {})


def paths(docs):
    return sorted(d.metadata["file_path"] for d in docs)


# ---------------------------------------------------------------- registration

def test_zip_is_a_supported_type_with_its_own_loader():
    assert ZIP_MIME_TYPE in SUPPORTED_MIME_TYPES
    assert isinstance(get_loader(ZIP_MIME_TYPE), ZipLoader)


# ---------------------------------------------------------------- normal project

def test_a_normal_project_is_read_with_paths_languages_and_tiers():
    docs, summary = load([
        ("app/main.py", PY), ("app/util.js", b"export const a = 1;\n"), ("README.md", b"# Title\n\nHello\n"),
        ("config.yaml", b"a: 1\n"), ("data/rows.csv", b"a,b\n1,2\n"),
    ])
    assert paths(docs) == ["README.md", "app/main.py", "app/util.js", "config.yaml", "data/rows.csv"]
    by_path = {d.metadata["file_path"]: d.metadata for d in docs}
    assert by_path["app/main.py"]["language"] == "python" and by_path["app/main.py"]["tier"] == "code"
    assert by_path["README.md"]["language"] == "markdown" and by_path["README.md"]["tier"] == "text"
    assert by_path["data/rows.csv"]["tier"] == "data"
    assert summary.accepted == 5 and summary.skipped == {}


def test_code_text_is_kept_exactly():
    source = b"def f():\r\n\treturn 1  \r\n"
    docs, _ = load([("a.py", source)])
    assert docs[0].page_content == source.decode()


def test_one_top_level_folder_is_stripped_like_a_github_download():
    docs, _ = load([("repo-main/app/main.py", PY), ("repo-main/README.md", b"# Hi\n")])
    assert paths(docs) == ["README.md", "app/main.py"]


def test_the_folder_is_kept_when_there_is_more_than_one_or_a_file_sits_at_the_root():
    docs, _ = load([("a/x.py", PY), ("b/y.py", PY)])
    assert paths(docs) == ["a/x.py", "b/y.py"]
    docs, _ = load([("a/x.py", PY), ("root.py", PY)])
    assert paths(docs) == ["a/x.py", "root.py"]


def test_macos_resource_forks_do_not_stop_the_folder_strip_and_are_skipped():
    docs, summary = load([("proj/a.py", PY), ("__MACOSX/proj/._a.py", b"\x00junk"), ("proj/b.py", PY)])
    assert paths(docs) == ["a.py", "b.py"]
    assert summary.skipped == {"ignored_dir": 1}


def test_output_order_is_by_path_so_runs_are_repeatable():
    docs, _ = load([("z.py", PY), ("a.py", PY), ("m/b.py", PY)])
    assert [d.metadata["file_path"] for d in docs] == ["a.py", "m/b.py", "z.py"]


def test_directory_entries_are_not_files_and_are_not_counted():
    docs, summary = load([("src/", b""), ("src/a.py", PY)])
    assert paths(docs) == ["a.py"] or paths(docs) == ["src/a.py"]
    assert summary.skipped == {}


# ---------------------------------------------------------------- hostile names (S2)

@pytest.mark.parametrize("name", ["../evil.py", "a/../../evil.py", "/abs/evil.py", "C:\\win\\evil.py", "..\\evil.py",
                                  "x" * 400 + ".py"])
def test_unsafe_names_are_skipped_not_read(name):
    docs, summary = load([(name, PY), ("ok.py", PY)])
    assert paths(docs) == ["ok.py"]
    assert summary.skipped == {"unsafe_path": 1}


def test_a_symlink_member_is_skipped():
    link = zipfile.ZipInfo("link.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    docs, summary = load([(link, b"/etc/passwd"), ("ok.py", PY)])
    assert paths(docs) == ["ok.py"] and summary.skipped == {"symlink": 1}


def test_an_encrypted_member_is_skipped():
    raw = bytearray(make_zip([("secret_notes.py", PY), ("ok.py", PY)]))
    # set the "encrypted" bit in the CENTRAL DIRECTORY header of the first entry (what zipfile reads first)
    index = raw.index(b"PK\x01\x02")
    flags = struct.unpack_from("<H", raw, index + 8)[0]
    struct.pack_into("<H", raw, index + 8, flags | 0x1)
    docs, summary = load(bytes(raw))
    assert summary.skipped.get("encrypted") == 1
    assert len(docs) == 1


def test_a_nested_archive_is_skipped_and_never_opened():
    inner = make_zip([("deep.py", PY)])
    docs, summary = load([("inner.zip", inner), ("ok.py", PY)])
    assert paths(docs) == ["ok.py"] and summary.skipped == {"nested_archive": 1}


def test_duplicate_paths_keep_the_first():
    docs, summary = load([("a.py", PY), ("a.py", b"print('second')\n"), ("b.py", PY)])
    assert paths(docs) == ["a.py", "b.py"] and summary.skipped == {"duplicate_path": 1}
    assert next(d for d in docs if d.metadata["file_path"] == "a.py").page_content == PY.decode()


# ---------------------------------------------------------------- policy rules inside a zip

def test_secrets_dependency_folders_lock_files_and_unsupported_types_are_skipped():
    docs, summary = load([
        ("ok.py", PY), (".env", b"KEY=abc\n"), ("keys/id_rsa.pem", b"-----BEGIN"), ("node_modules/lib/x.js", b"var a=1;\n"),
        ("package-lock.json", b"{}"), ("logo.png", b"\x89PNG\r\n"), ("app.min.js", b"var a=1;"), (".env.example", b"KEY=\n"),
    ])
    assert paths(docs) == [".env.example", "ok.py"]
    assert summary.skipped == {"secret_file": 2, "ignored_dir": 1, "ignored_file": 2, "unsupported_type": 1}
    assert "KEY=abc" not in "".join(d.page_content for d in docs)


def test_binary_and_non_utf8_and_empty_and_minified_files_are_skipped():
    docs, summary = load([
        ("ok.py", PY), ("bin.py", b"\x00\x01\xff\xfe\x80"), ("latin.py", "caf\xe9 = 1\n".encode("latin-1")),
        ("empty.py", b"\n\n  \n"), ("mini.js", b"var a=" + b"1+" * 2000 + b"1;\n"),
    ])
    assert paths(docs) == ["ok.py"]
    assert summary.skipped == {"not_utf8": 2, "empty": 1, "minified_or_generated": 1}


def test_a_bom_is_dropped_from_code():
    docs, _ = load([("a.py", b"\xef\xbb\xbfx = 1\n")])
    assert docs[0].page_content == "x = 1\n"


# ---------------------------------------------------------------- limits (S1, S3, S4, S9, S17)

def test_only_the_first_500_files_are_read_and_the_rest_are_counted():
    docs, summary = load([(f"f{i:04d}.py", b"x = %d\n" % i) for i in range(1000)])
    assert len(docs) == policy.MAX_FILES == 500
    assert summary.skipped == {"too_many_files": 500}


def test_a_file_over_its_size_cap_is_skipped():
    big = b"# comment line\n" * 100_000          # 1.5 MB of code, cap is 1 MB
    docs, summary = load([("big.py", big), ("ok.py", PY)])
    assert paths(docs) == ["ok.py"] and summary.skipped == {"too_large": 1}


def test_total_unzipped_size_is_capped_and_the_rest_is_counted(monkeypatch):
    monkeypatch.setattr(policy, "MAX_ZIP_UNCOMPRESSED", 3_000_000)
    from app.ingestion.loaders import zip_loader
    monkeypatch.setattr(zip_loader, "MAX_ZIP_UNCOMPRESSED", 3_000_000)
    body = b"# line of text\n" * 40_000             # 600 KB each
    docs, summary = load([(f"f{i}.py", body) for i in range(10)])
    assert 1 <= len(docs) <= 5
    assert summary.skipped.get("zip_size_limit", 0) == 10 - len(docs)
    assert sum(len(d.page_content) for d in docs) <= 3_000_000


def test_a_lying_header_never_gives_more_than_the_cap_and_never_crashes():
    raw = bytearray(make_zip([("liar.py", b"# x\n" * 600_000), ("ok.py", PY)]))   # 1.8 MB real
    index = raw.index(b"PK\x01\x02")
    struct.pack_into("<I", raw, index + 24, 50)                                    # declared size: 50 bytes
    docs, summary = load(bytes(raw))
    assert "ok.py" in paths(docs)
    assert all(len(d.page_content) <= policy.MAX_FILE_BYTES["code"] for d in docs)
    assert "liar.py" not in paths(docs)


def test_a_compression_bomb_is_skipped():
    bomb = b"\x00" * 30_000_000                                                    # 30 MB of zeros compresses ~1000x
    docs, summary = load([("zeros.txt", bomb), ("ok.py", PY)])
    assert paths(docs) == ["ok.py"]
    assert sum(summary.skipped.values()) == 1


def test_too_many_entries_in_the_central_directory_is_refused(monkeypatch):
    from app.ingestion.loaders import zip_loader
    monkeypatch.setattr(zip_loader, "MAX_ZIP_ENTRIES", 5)
    with pytest.raises(ValueError, match="too many"):
        load([(f"d{i}/", b"") for i in range(10)] + [("a.py", PY)])


# ---------------------------------------------------------------- failures are clear

def test_not_a_zip_is_refused_with_a_clear_message():
    with pytest.raises(ValueError, match="Not a valid zip"):
        ZipLoader().load_with_summary(b"this is not a zip", "x.zip", {})


def test_an_empty_zip_and_a_zip_without_usable_files_fail_clearly():
    for entries in ([], [("logo.png", b"\x89PNG"), ("node_modules/a.js", b"var a;")]):
        with pytest.raises(ValueError, match="No usable files in the zip"):
            load(entries) if entries else ZipLoader().load_with_summary(make_zip([]), "e.zip", {})


def test_one_bad_file_does_not_fail_the_zip():
    docs, summary = load([("bad.py", b"\xff\xfe\x00"), ("good.py", PY)])
    assert paths(docs) == ["good.py"] and summary.accepted == 1


def test_the_summary_describes_counts_and_reasons_but_never_file_names_or_content():
    _, summary = load([("ok.py", PY), (".env", b"TOKEN=hunter2\n"), ("a.png", b"x")])
    text = summary.describe()
    assert "1 file" in text and "secret_file" in text
    assert "hunter2" not in text and ".env" not in text


# ---------------------------------------------------------------- tiers 2-4

def test_notebook_keeps_cells_and_drops_outputs():
    notebook = {
        "metadata": {"kernelspec": {"language": "python"}},
        "cells": [
            {"cell_type": "markdown", "source": ["# Analysis\n", "Intro"]},
            {"cell_type": "code", "source": "x = 1\nprint(x)", "outputs": [{"output_type": "stream", "text": ["SECRET_OUTPUT_TOKEN"]}]},
            {"cell_type": "raw", "source": "ignored"},
        ],
    }
    docs, _ = load([("nb.ipynb", json.dumps(notebook).encode())])
    text = docs[0].page_content
    assert docs[0].metadata["tier"] == "notebook"
    assert "# Analysis" in text and "x = 1" in text and "print(x)" in text
    assert "SECRET_OUTPUT_TOKEN" not in text and "ignored" not in text


def test_a_broken_notebook_is_skipped():
    docs, summary = load([("bad.ipynb", b"{not json"), ("ok.py", PY)])
    assert paths(docs) == ["ok.py"] and summary.skipped == {"unreadable": 1}


def test_a_csv_keeps_only_the_header_and_the_first_rows():
    rows = b"id,name\n" + b"".join(b"%d,name%d\n" % (i, i) for i in range(500))
    docs, _ = load([("people.csv", rows)])
    lines = docs[0].page_content.splitlines()
    assert lines[0] == "id,name" and len(lines) == policy.DATA_SAMPLE_ROWS + 1
    assert "name499" not in docs[0].page_content


def test_a_csv_sample_is_capped_in_bytes():
    rows = b"a,b\n" + b"".join(b"%d,%s\n" % (i, b"x" * 900) for i in range(30))
    docs, _ = load([("wide.csv", rows)])
    assert len(docs[0].page_content.encode()) <= policy.DATA_SAMPLE_MAX_BYTES


# ---------------------------------------------------------------- chunking

def chunk_zip(entries, **config):
    docs, _ = load(entries)
    return ChunkingOrchestrator(ChunkingConfig(**config)).chunk_batch(docs, mime_type=ZIP_MIME_TYPE)


def test_every_chunk_carries_its_own_file_path_and_lines_and_indexes_are_unique():
    big = "".join(f"def func_{i}(x):\n    return x + {i}\n\n\n" for i in range(80)).encode()
    chunks = chunk_zip([("pkg/a.py", big), ("pkg/b.py", PY), ("README.md", b"# T\n\nBody text here.\n")])
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))          # A4: unique across files
    assert {c.metadata["file_path"] for c in chunks} == {"pkg/a.py", "pkg/b.py", "README.md"}
    for c in chunks:
        assert c.metadata["start_line"] >= 1 and c.metadata["end_line"] >= c.metadata["start_line"]
    a_chunks = [c for c in chunks if c.metadata["file_path"] == "pkg/a.py"]
    assert len(a_chunks) > 1 and a_chunks[0].metadata["chunker"] == "ast"


def test_chunk_lines_point_at_the_right_lines_of_the_right_file():
    chunks = chunk_zip([("m.py", PY)])
    assert chunks[0].metadata["start_line"] == 1 and chunks[0].metadata["end_line"] == PY.decode().count("\n")


def test_a_csv_sample_stays_one_chunk_and_a_notebook_splits_by_cell():
    nb = {"cells": [{"cell_type": "code", "source": "a = %d\n" % i + "# pad " * 80, "outputs": []} for i in range(20)]}
    chunks = chunk_zip([("d.csv", b"a,b\n1,2\n"), ("n.ipynb", json.dumps(nb).encode())], chunk_size=128, chunk_overlap=0)
    assert sum(c.metadata["file_path"] == "d.csv" for c in chunks) == 1
    assert sum(c.metadata["file_path"] == "n.ipynb" for c in chunks) > 1


def test_one_file_that_cannot_be_chunked_does_not_lose_the_others(monkeypatch):
    from app.ingestion.chunking import strategies

    original = strategies.CodeChunkingStrategy.split

    def flaky(self, document):
        if document.metadata["file_path"] == "bad.py":
            raise RuntimeError("boom")
        return original(self, document)

    monkeypatch.setattr(strategies.CodeChunkingStrategy, "split", flaky)
    chunks = chunk_zip([("bad.py", PY), ("good.py", PY)])
    assert {c.metadata["file_path"] for c in chunks} == {"good.py"}


# ---------------------------------------------------------------- the real pipeline, fake embedder

@pytest.fixture
def recorded_chunks(monkeypatch):
    import importlib

    # the module that `from app.ingestion.pipeline import ingest_file` really uses (other tests may re-import it,
    # which leaves `from app.ingestion import pipeline` pointing at a stale copy)
    pipeline = importlib.import_module("app.ingestion.pipeline")

    captured: list[Document] = []

    class FakeEmbedder:
        def embed_and_index(self, chunks):
            captured.extend(chunks)
            return [f"p{i}" for i in range(len(chunks))]

    monkeypatch.setattr(pipeline, "get_embedding_orchestrator", lambda: FakeEmbedder())
    return captured


def test_pipeline_ingests_a_zip_and_reports_what_it_skipped(recorded_chunks):
    from app.ingestion.pipeline import ingest_file

    data = make_zip([("p/a.py", PY), ("p/.env", b"KEY=1\n"), ("p/README.md", b"# Hi\n\nText\n")])
    result = ingest_file(data, "proj.zip", ZIP_MIME_TYPE, {"document_id": "1"})
    assert result.success, result.error
    assert result.num_chunks == len(recorded_chunks) > 0
    assert any("secret_file" in w for w in result.warnings)
    assert {c.metadata["file_path"] for c in recorded_chunks} == {"a.py", "README.md"}
    assert all(c.metadata["document_id"] == "1" for c in recorded_chunks)        # document metadata reaches every chunk


def test_pipeline_does_not_clean_code_inside_a_zip(recorded_chunks):
    from app.ingestion.pipeline import ingest_file

    source = b"def f(x):\n    if x:\n        return None\n    if not x:\n        return None\n    return None\n"
    result = ingest_file(make_zip([("f.py", source)]), "p.zip", ZIP_MIME_TYPE, {"document_id": "1"})
    assert result.success, result.error
    assert recorded_chunks[0].page_content.count("return None") == 3


def test_pipeline_fails_a_zip_with_nothing_usable_with_a_friendly_reason(recorded_chunks):
    from app.ingestion.pipeline import ingest_file

    result = ingest_file(make_zip([("logo.png", b"x")]), "p.zip", ZIP_MIME_TYPE, {"document_id": "1"})
    assert result.success is False and recorded_chunks == []
    assert "no source" in friendly_failure_reason("failed", result.error).lower()


def test_friendly_reasons_for_the_other_zip_failures():
    for error in ["Not a valid zip file", "Zip has too many entries", "Processing took too long"]:
        reason = friendly_failure_reason("failed", error)
        assert reason and reason != "Processing failed. Please try uploading the file again."


# ---------------------------------------------------------------- HTTP: chat mode rules (S12)

@pytest.fixture
def upload_client(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.db.database import get_db
    from app.db.models import User
    from app.dependencies.auth import get_current_user
    from app.routers.conversations import router as conversations_router
    from app.routers.document import router
    from app.worker.celery_app import celery_app
    from tests.conftest import unique_clerk_id

    monkeypatch.setattr(celery_app, "send_task", lambda *a, **kw: None)
    user = User(clerk_user_id=unique_clerk_id(), email="zip@example.com")
    db.add(user)
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.include_router(conversations_router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _chat(client, mode):
    resp = client.post("/conversations", json={"mode": mode})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.parametrize("content_type", ["application/zip", "application/x-zip-compressed", "application/octet-stream", ""])
def test_a_zip_goes_into_a_code_chat_whatever_the_browser_calls_it(upload_client, content_type):
    chat = _chat(upload_client, "code")
    resp = upload_client.post("/documents", data={"conversation_id": chat},
                              files={"file": ("project.zip", make_zip([("a.py", PY)]), content_type)})
    assert resp.status_code == 201, resp.text
    assert resp.json()["mime_type"] == ZIP_MIME_TYPE


def test_a_docs_chat_refuses_a_zip_on_the_server(upload_client):
    chat = _chat(upload_client, "docs")
    resp = upload_client.post("/documents", data={"conversation_id": chat},
                              files={"file": ("project.zip", make_zip([("a.py", PY)]), "application/zip")})
    assert resp.status_code == 400 and "codebase" in resp.json()["detail"].lower()


def test_a_code_chat_still_refuses_documents(upload_client):
    chat = _chat(upload_client, "code")
    resp = upload_client.post("/documents", data={"conversation_id": chat}, files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert resp.status_code == 400


def test_a_file_named_zip_that_is_not_a_zip_is_refused_before_it_is_stored(upload_client):
    chat = _chat(upload_client, "code")
    resp = upload_client.post("/documents", data={"conversation_id": chat}, files={"file": ("fake.zip", b"just text", "application/zip")})
    assert resp.status_code == 400 and "zip" in resp.json()["detail"].lower()


# ---------------------------------------------------------------- INTEGRATION: real worker, models, Qdrant

def test_a_project_zip_reaches_ready_and_its_files_are_searchable(client, worker, qdrant, user_headers):
    from app.ingestion.embedding.models import EmbeddingConfig
    from app.ingestion.embedding.vector_store import get_vector_store
    from app.retrieval.filters import build_qdrant_filter

    data = make_zip([
        ("myproj-main/app/limiter.py", b'class TokenBucket:\n    """Refills one token every second."""\n\n    def take_token(self):\n        return True\n'),
        ("myproj-main/app/names.py", PY),
        ("myproj-main/.env", b"API_KEY=do-not-index-me\n"),
        ("myproj-main/node_modules/x/index.js", b"var skipped = 1;\n"),
        ("myproj-main/README.md", b"# My project\n\nA small demo project.\n"),
    ])
    doc = _upload(client, user_headers, "myproj.zip", data, "application/zip")
    assert doc["mime_type"] == ZIP_MIME_TYPE
    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready", _error_message(doc["id"])

    points = _points(qdrant, doc["id"])
    assert points
    metas = [p.payload["metadata"] for p in points]
    assert {m["file_path"] for m in metas} == {"app/limiter.py", "app/names.py", "README.md"}
    assert all(m["doc_type"] == "code" and m["source_name"] == "myproj.zip" for m in metas)
    assert "do-not-index-me" not in "".join(p.payload["page_content"] for p in points)
    assert sorted(m["chunk_index"] for m in metas) == list(range(len(metas)))

    store = get_vector_store(EmbeddingConfig())
    hits = store.similarity_search("how does take_token work?", k=3,
                                   filter=build_qdrant_filter(uploaded_by=metas[0]["uploaded_by"]))
    assert hits and hits[0].metadata["file_path"] == "app/limiter.py"
    assert "take_token" in hits[0].page_content


def test_a_hostile_zip_fails_cleanly_through_the_real_worker(client, worker, qdrant, user_headers):
    data = make_zip([("../evil.py", PY), (".env", b"K=1\n"), ("logo.png", b"x")])
    doc = _upload(client, user_headers, "hostile.zip", data, "application/zip")
    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "failed"
    assert "no source" in final["failure_reason"].lower()
    assert _points(qdrant, doc["id"]) == []
