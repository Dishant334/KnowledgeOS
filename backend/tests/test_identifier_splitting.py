# tests/test_identifier_splitting.py
#
# Stage 7: identifier-aware keyword search, CODE MODE ONLY.
#   * the splitter (pure text -> text)
#   * the switch (a context variable the BM25 embedder reads)
#   * the wiring: indexing a code chunk and searching from a code chat turn the switch on; docs never do
#   * REAL BM25 (fastembed, local model): "token" really shares a keyword with take_token once split
# No Qdrant, no LLM.

from langchain_core.documents import Document

from app.core.config import settings
from app.ingestion.embedding import identifiers
from app.ingestion.embedding.identifiers import expand_identifiers, splitting, splitting_enabled


# ---------------------------------------------------------------- the splitter

def parts_added(text: str) -> list[str]:
    """The words the splitter appends (empty when it leaves the text alone)."""
    out = expand_identifiers(text)
    assert out.startswith(text)                      # the original text is never changed, only extended
    return out[len(text):].split()


def test_snake_case_is_split_and_the_original_stays():
    out = expand_identifiers("def take_token(bucket):")
    assert "take_token" in out                       # the original identifier is still there
    assert parts_added("def take_token(bucket):") == ["take", "token"]


def test_camel_and_pascal_case_are_split():
    assert parts_added("getUserName") == ["get", "user", "name"]
    assert parts_added("class TokenBucket:") == ["token", "bucket"]


def test_acronyms_stay_together_inside_a_name():
    assert parts_added("HTTPServer") == ["http", "server"]
    assert parts_added("parseJSONBody") == ["parse", "json", "body"]


def test_leading_and_trailing_underscores_and_digits():
    assert parts_added("_make_id") == ["make", "id"]
    assert parts_added("__init__") == []             # one real word, nothing to add
    assert parts_added("MAX_FILE_BYTES") == ["max", "file", "bytes"]
    assert parts_added("sha256_hex") == ["sha256", "hex"]


def test_words_without_a_split_leave_the_text_untouched():
    for text in ["", "   ", "plain English sentence.", "Hello World", "Dockerfile", "x = 1"]:
        assert expand_identifiers(text) == text


def test_every_occurrence_counts_because_keyword_search_counts_repeats():
    assert parts_added("take_token(); take_token()") == ["take", "token", "take", "token"]


def test_single_letters_are_not_added():
    assert parts_added("a_b_cat") == ["cat"]


def test_does_not_crash_on_odd_input():
    for text in ["é_ü", "日本語_テキスト", "a" * 5000 + "_" + "b" * 5000, "\x00_\x01", "___", "_"]:
        assert isinstance(expand_identifiers(text), str)


# ---------------------------------------------------------------- the switch

def test_the_switch_is_off_by_default_and_restored_afterwards():
    assert splitting_enabled() is False
    with splitting(True):
        assert splitting_enabled() is True
        with splitting(False):
            assert splitting_enabled() is False
        assert splitting_enabled() is True
    assert splitting_enabled() is False


def test_the_switch_is_restored_even_after_an_error():
    try:
        with splitting(True):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert splitting_enabled() is False


# ---------------------------------------------------------------- the real BM25 embedder

def _embedder():
    from app.ingestion.embedding.embedders import BM25SparseEmbedder
    from app.ingestion.embedding.models import EmbeddingConfig
    return BM25SparseEmbedder(EmbeddingConfig())


def _shares_a_keyword(a, b) -> bool:
    return bool(set(a.indices) & set(b.indices))


def test_real_bm25_matches_token_with_take_token_only_when_splitting_is_on():
    embedder = _embedder()
    # off: take_token is ONE keyword, so the query word "token" has nothing to match
    with splitting(False):
        off_doc = embedder.embed_documents(["def take_token(self):\n    pass"])[0]
        off_query = embedder.embed_query("token")
    assert not _shares_a_keyword(off_doc, off_query)
    with splitting(True):
        on_doc = embedder.embed_documents(["def take_token(self):\n    pass"])[0]
        on_query = embedder.embed_query("token")
    assert _shares_a_keyword(on_doc, on_query)


def test_real_bm25_query_side_is_split_too():
    embedder = _embedder()
    with splitting(True):
        doc = embedder.embed_documents(["the token bucket refills"])[0]
        query = embedder.embed_query("TokenBucket")
    assert _shares_a_keyword(doc, query)                 # the query identifier was split into token + bucket


def test_real_bm25_without_the_switch_is_exactly_the_old_behaviour():
    embedder = _embedder()
    text = "def take_token(self): return get_user_name()"
    plain = embedder.embed_documents([text])[0]
    again = embedder.embed_documents([text])[0]
    assert list(plain.indices) == list(again.indices)
    with splitting(True):
        split = embedder.embed_documents([text])[0]
    assert len(split.indices) > len(plain.indices)


# ---------------------------------------------------------------- wiring: indexing

class _FakeStore:
    def __init__(self):
        self.seen = []

    def add_documents(self, documents, ids):
        self.seen.append(splitting_enabled())

    def similarity_search_with_score(self, query, k, filter=None):
        self.seen.append(splitting_enabled())
        return []


def _orchestrator(store):
    from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator
    from app.ingestion.embedding.models import EmbeddingConfig
    orchestrator = EmbeddingOrchestrator.__new__(EmbeddingOrchestrator)
    orchestrator.config = EmbeddingConfig()
    orchestrator.vector_store = store
    return orchestrator


def _chunk(doc_type, text="x"):
    return Document(page_content=text, metadata={"source": "f", "chunk_index": 0, "doc_type": doc_type})


def test_indexing_code_chunks_turns_the_switch_on(monkeypatch):
    monkeypatch.setattr(settings, "code_split_identifiers", True)
    store = _FakeStore()
    _orchestrator(store).embed_and_index([_chunk("code")])
    assert store.seen == [True]
    assert splitting_enabled() is False                   # and it is back off afterwards


def test_indexing_documents_never_turns_it_on(monkeypatch):
    monkeypatch.setattr(settings, "code_split_identifiers", True)
    for doc_type in ["pdf", "md", "txt", "csv", "docx"]:
        store = _FakeStore()
        _orchestrator(store).embed_and_index([_chunk(doc_type)])
        assert store.seen == [False], doc_type


def test_the_setting_can_turn_code_splitting_off(monkeypatch):
    monkeypatch.setattr(settings, "code_split_identifiers", False)
    store = _FakeStore()
    _orchestrator(store).embed_and_index([_chunk("code")])
    assert store.seen == [False]


# ---------------------------------------------------------------- wiring: searching

def test_hybrid_search_uses_the_switch_only_when_asked(monkeypatch):
    from app.retrieval.hybrid_search import hybrid_search
    store = _FakeStore()
    hybrid_search(store, "q", k=3)
    hybrid_search(store, "q", k=3, split_identifiers=True)
    assert store.seen == [False, True]
    assert splitting_enabled() is False


def test_retrieve_splits_only_for_a_code_chat(monkeypatch):
    from app.retrieval import orchestrator as retrieval

    seen = []

    def fake_search(store, query, k, qdrant_filter=None, split_identifiers=False):
        seen.append(split_identifiers)
        return []

    class _Reranker:
        def rerank(self, q, c, top_k):
            return []

    monkeypatch.setattr(retrieval, "hybrid_search", fake_search)
    monkeypatch.setattr(retrieval, "get_search_store", lambda: object())
    monkeypatch.setattr(retrieval, "get_reranker", lambda name: _Reranker())
    monkeypatch.setattr(settings, "code_split_identifiers", True)

    retrieval.retrieve("q", user_id=1)                    # default: a documents chat
    retrieval.retrieve("q", user_id=1, mode="docs")
    retrieval.retrieve("q", user_id=1, mode="code")
    assert seen == [False, False, True]

    monkeypatch.setattr(settings, "code_split_identifiers", False)
    retrieval.retrieve("q", user_id=1, mode="code")
    assert seen[-1] is False


def test_the_module_exposes_no_state_between_threads():
    # a context variable, not a global: two threads must not see each other's switch
    import threading
    result = {}

    def worker():
        result["other"] = splitting_enabled()

    with splitting(True):
        t = threading.Thread(target=worker)
        t.start()
        t.join()
    assert result["other"] is False
    assert identifiers.splitting_enabled() is False
