# CODEBASE-FEATURE (Stage 3): citations that carry file path, line numbers and language.
#
# UNIT (no services): line numbers computed by the chunker, the citation mapper, the code snippet,
#   the dataclass -> API model conversion used by /ask.
# API (real Postgres): saved citations come back with the new fields; answers saved before this
#   stage (no such keys) still load.
# INTEGRATION: a REAL Celery worker + models + Qdrant: the stored line numbers slice the uploaded
#   file back to the stored chunk.
from dataclasses import asdict

import pytest
from langchain_core.documents import Document

from app.augmentation.citation_mapper import SNIPPET_CHARS, build_citations, make_code_snippet, make_snippet
from app.ingestion.chunking.model import ChunkingConfig
from app.ingestion.chunking.orchestrator import ChunkingOrchestrator
from app.ingestion.chunking.strategies import add_line_numbers
from app.ingestion.loaders.code_loader import CODE_MIME_TYPE, CodeLoader
from app.retrieval.model import ScoredChunk
from app.schemas.ask import Citation as ApiCitation

from tests.test_retrieve_ask_api import headers_for, users  # noqa: F401  (shared fixtures)

# Fixtures/helpers of the real-worker tests, reused for the integration test below.
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


def numbered_source(lines=200, newline="\n"):
    """Every line is different, so a chunk can be matched to exactly one place in the file."""
    return "".join(f"value_{i:03d} = {i}{newline}" for i in range(1, lines + 1))


def chunk_code(source, filename="numbers.py", **config):
    docs = CodeLoader().load(source.encode(), filename, {"document_id": "1"})
    return ChunkingOrchestrator(ChunkingConfig(**config)).chunk_batch(docs, mime_type=CODE_MIME_TYPE)


def lines_of(source, chunk):
    """The file lines a chunk claims to cover, joined back together."""
    start, end = chunk.metadata["start_line"], chunk.metadata["end_line"]
    return "".join(source.splitlines(keepends=True)[start - 1:end])


# --- line numbers from the chunker --------------------------------------------------------------


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_every_chunk_names_exactly_the_lines_it_covers(newline):
    source = numbered_source(200, newline)
    chunks = chunk_code(source, chunk_size=60, chunk_overlap=0)
    assert len(chunks) > 5
    for chunk in chunks:
        assert lines_of(source, chunk).strip("\r\n") == chunk.page_content.strip("\r\n")
    assert chunks[0].metadata["start_line"] == 1
    assert chunks[-1].metadata["end_line"] == 200


def test_overlapping_chunks_still_point_inside_the_file_in_order():
    source = numbered_source(200)
    chunks = chunk_code(source, chunk_size=60, chunk_overlap=20)
    starts = [c.metadata["start_line"] for c in chunks]
    assert starts == sorted(starts) and len(set(starts)) == len(starts)     # never two chunks from one line
    for chunk in chunks:
        assert 1 <= chunk.metadata["start_line"] <= chunk.metadata["end_line"] <= 200
        assert chunk.page_content.strip("\r\n") in lines_of(source, chunk)  # the chunk text lies within those lines


def test_a_small_file_is_one_chunk_from_line_one_to_the_last_line():
    source = "import os\n\n\ndef f():\n    return os.getcwd()\n"
    [chunk] = chunk_code(source, "f.py")
    assert (chunk.metadata["start_line"], chunk.metadata["end_line"]) == (1, 5)


def test_a_chunk_that_starts_with_the_newline_ending_the_previous_line_counts_from_its_first_real_line():
    # The splitter keeps the separator, so chunks often begin with "\n"; that newline belongs to the line before.
    source = "a = 1\nb = 2\nc = 3\nd = 4\n"
    chunks = [Document(page_content="\nb = 2\nc = 3", metadata={}), Document(page_content="\nd = 4\n", metadata={})]
    add_line_numbers(source, chunks)
    assert [(c.metadata["start_line"], c.metadata["end_line"]) for c in chunks] == [(2, 3), (4, 4)]


def test_a_chunk_that_cannot_be_found_gets_no_line_numbers_and_nothing_crashes():
    chunks = [Document(page_content="not in the file", metadata={"keep": 1})]
    add_line_numbers("a = 1\n", chunks)
    assert "start_line" not in chunks[0].metadata and chunks[0].metadata["keep"] == 1


def test_a_repetitive_file_gets_plausible_monotonic_lines():
    source = "def f(x):\n    return x\n\n" * 80
    chunks = chunk_code(source, chunk_size=40, chunk_overlap=0)
    starts = [c.metadata["start_line"] for c in chunks]
    assert starts == sorted(starts)
    assert all(1 <= c.metadata["start_line"] <= c.metadata["end_line"] <= 240 for c in chunks)


# --- the citation mapper ------------------------------------------------------------------------------


def scored(text="some text", **metadata):
    base = {"document_id": "1", "source_name": "a.pdf"}
    return ScoredChunk(document=Document(page_content=text, metadata={**base, **metadata}))


CODE_TEXT = "def verify(token):\n    if not token:\n        return None\n    return decode(token)\n"


def test_code_citations_carry_path_lines_language_and_the_exact_code():
    [c] = build_citations([scored(CODE_TEXT, source_name="app.zip", file_path="auth/jwt.py",
                                  start_line=40, end_line=43, language="python")])
    assert (c.file_path, c.start_line, c.end_line, c.language) == ("auth/jwt.py", 40, 43, "python")
    assert c.snippet == CODE_TEXT.rstrip()                 # newlines AND indentation survive
    assert "\n        return None\n" in c.snippet


def test_a_long_code_snippet_is_cut_at_the_cap_and_marked_without_losing_its_layout():
    code = "".join(f"    line_{i} = {i}\n" for i in range(200))
    snippet = build_citations([scored(code, language="python")])[0].snippet
    assert snippet.endswith("...") and len(snippet) <= SNIPPET_CHARS + 3
    assert snippet.startswith("    line_0 = 0\n    line_1 = 1\n")


def test_document_citations_are_unchanged_and_have_no_code_fields():
    [c] = build_citations([scored("Employees   get\n\ntwenty days.", page_number=7)])
    assert c.page_number == 7 and c.snippet == "Employees get twenty days."          # prose: whitespace tidied
    assert (c.file_path, c.start_line, c.end_line, c.language) == (None, None, None, None)


def test_make_code_snippet_drops_leading_blank_lines_and_trailing_space_only():
    assert make_code_snippet("\n\n    x = 1\n    y = 2  \n\n") == "    x = 1\n    y = 2"
    assert make_code_snippet("x" * SNIPPET_CHARS) == "x" * SNIPPET_CHARS
    assert make_snippet("a   b") == "a b"                                            # the prose helper is untouched


# --- from the mapper to the API model (what /ask returns) ----------------------------------------------------


def test_the_dataclass_converts_to_the_api_model_with_the_new_fields():
    # services/ask.py does exactly this: Citation(**asdict(citation)); a field on only one side would raise.
    [c] = build_citations([scored(CODE_TEXT, file_path="a.py", start_line=1, end_line=4, language="python")])
    api = ApiCitation(**asdict(c))
    assert api.model_dump()["file_path"] == "a.py"
    assert (api.start_line, api.end_line, api.language) == (1, 4, "python")


def test_an_old_citation_without_the_new_fields_still_validates():
    api = ApiCitation.model_validate({"marker": "[1]", "document_id": 3, "source_name": "old.pdf", "page_number": 2})
    assert (api.file_path, api.start_line, api.end_line, api.language) == (None, None, None, None)


# --- the API: saved citations come back whole -------------------------------------------------------------------


def test_saved_code_citations_and_old_citations_both_come_back_from_the_conversation(client, users, db):
    from app.db.models import Conversation, Message

    conversation = Conversation(user_id=users[0].id, title="code chat")
    db.add(conversation)
    db.flush()
    new = {"marker": "[1]", "document_id": 5, "source_name": "app.zip", "snippet": "def f():\n    pass",
           "file_path": "src/app.py", "start_line": 10, "end_line": 12, "language": "python"}
    old = {"marker": "[1]", "document_id": 6, "source_name": "old.pdf", "page_number": 3, "snippet": "text"}  # saved before Stage 3
    db.add(Message(conversation_id=conversation.id, role="assistant", content="see [1]", citations=[new]))
    db.add(Message(conversation_id=conversation.id, role="assistant", content="see [1]", citations=[old]))
    db.commit()

    resp = client.get(f"/conversations/{conversation.public_id}", headers=headers_for(users[0]))
    assert resp.status_code == 200, resp.text
    first, second = [m["citations"][0] for m in resp.json()["messages"]]
    assert (first["file_path"], first["start_line"], first["end_line"], first["language"]) == ("src/app.py", 10, 12, "python")
    assert first["snippet"] == "def f():\n    pass"
    assert (second["file_path"], second["start_line"], second["end_line"], second["language"]) == (None, None, None, None)
    assert second["page_number"] == 3


# --- INTEGRATION: real worker, real models, real Qdrant ---------------------------------------------------------


def test_stored_line_numbers_slice_the_uploaded_file_back_to_the_stored_chunk(client, worker, qdrant, user_headers):
    # ~230 distinct lines: well over one 512-token chunk, so the file is split into several.
    source = "\n".join(f"def handler_{i:03d}(request):\n    return respond(request, status={i})\n" for i in range(1, 116))
    doc = _upload(client, user_headers, "handlers.py", source.encode(), "application/octet-stream")
    final, _ = _wait(client, user_headers, doc["id"], worker=worker)
    assert final["status"] == "ready", _error_message(doc["id"])

    points = sorted(_points(qdrant, doc["id"]), key=lambda p: p.payload["metadata"]["chunk_index"])
    assert len(points) >= 2
    file_lines = source.splitlines(keepends=True)
    previous_start = 0
    for p in points:
        meta, text = p.payload["metadata"], p.payload["page_content"]
        start, end = meta["start_line"], meta["end_line"]
        assert 1 <= start <= end <= len(file_lines) and start > previous_start
        assert text.strip("\n") in "".join(file_lines[start - 1:end])
        previous_start = start
    assert points[0].payload["metadata"]["start_line"] == 1
