"""
Retrieval / augmentation / generation helpers — UNIT tests.
No Qdrant, no embedding models, no database. LLM steps use a fake model.
"""

import importlib
import sys

import pytest
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from app.augmentation.context_builder import ContextBuilder
from app.generation.orchestrator import NO_ANSWER, generate_answer
from app.retrieval.filters import build_qdrant_filter
from app.retrieval.merge import merge_and_truncate
from app.retrieval.model import ScoredChunk
from app.retrieval.orchestrator import make_query_variants, rewrite_question
from tests.conftest import make_fake_llm


def chunk(text, fused=None, **metadata):
    return ScoredChunk(document=Document(page_content=text, metadata=metadata), fused_score=fused)


def broken_llm():
    def fail(prompt_value):
        raise RuntimeError("llm is down")

    return RunnableLambda(fail)


# --- filters ----------------------------------------------------------------------


def test_filter_is_none_without_conditions():
    assert build_qdrant_filter() is None


def test_filter_combines_user_document_and_type():
    flt = build_qdrant_filter(uploaded_by="7", doc_type="pdf", document_ids=["3", "4"])
    keys = {cond.key: cond for cond in flt.must}
    assert set(keys) == {"metadata.uploaded_by", "metadata.doc_type", "metadata.document_id"}
    assert keys["metadata.uploaded_by"].match.value == "7"
    assert keys["metadata.document_id"].match.any == ["3", "4"]


# --- merge / fusion bookkeeping ---------------------------------------------------


def test_merge_keeps_best_score_per_chunk_sorts_and_truncates():
    chunks = [
        chunk("a", 0.2, id="a"), chunk("b", 0.9, id="b"),
        chunk("a", 0.7, id="a"),                      # same chunk again, better score
        chunk("c", 0.5, id="c"),
    ]
    merged = merge_and_truncate(chunks, id_fn=lambda d: d.metadata["id"], pool_size=2)
    assert [c.document.metadata["id"] for c in merged] == ["b", "a"]
    assert merged[1].fused_score == 0.7


# --- query rewriting / multi-query fallbacks ----------------------------------------


def test_rewrite_skipped_without_history():
    calls = []
    llm = make_fake_llm(calls=calls)
    assert rewrite_question(llm, "what is the policy?", history="") == "what is the policy?"
    assert calls == []  # no LLM call for a first message


def test_rewrite_uses_history():
    llm = make_fake_llm(rewritten="What is the 2023 vacation policy?")
    out = rewrite_question(llm, "and 2023?", history="User: vacation policy?\nAssistant: 20 days.")
    assert out == "What is the 2023 vacation policy?"


def test_rewrite_falls_back_when_llm_fails():
    assert rewrite_question(broken_llm(), "and 2023?", history="User: x") == "and 2023?"


def test_variants_dedupe_and_include_original():
    llm = make_fake_llm(variants=["vacation days", "vacation days", "annual leave"])
    variants = make_query_variants(llm, "vacation policy", num_variants=4)
    assert variants == ["vacation policy", "vacation days", "annual leave"]


def test_variants_fall_back_when_llm_fails():
    assert make_query_variants(broken_llm(), "vacation policy", 4) == ["vacation policy"]


# --- context builder: citation numbers match the text ----------------------------------


def test_context_builder_numbers_only_used_chunks():
    big = "word " * 400
    chunks = [
        chunk("First short chunk.", document_id="1", source_name="a.pdf", page_number=1),
        chunk(big, document_id="2", source_name="huge.pdf"),                     # over budget, skipped
        chunk("Third short chunk.", document_id="3", source_name="c.pdf", page_number=4),
    ]
    built = ContextBuilder(max_context_tokens=100).build(chunks)

    assert built.chunks_used == 2 and built.chunks_dropped == 1
    assert [c.marker for c in built.citations] == ["[1]", "[2]"]
    assert [c.document_id for c in built.citations] == ["1", "3"]       # huge.pdf is not cited
    assert "[1] First short chunk." in built.prompt_context
    assert "[2] Third short chunk." in built.prompt_context
    assert "[3]" not in built.prompt_context


# --- generation ---------------------------------------------------------------------------


def test_no_chunks_means_no_llm_call_and_abstain():
    calls = []
    result = generate_answer("anything?", make_fake_llm(calls=calls), chunks=[])
    assert result.answer == NO_ANSWER and result.abstained and result.citations == []
    assert calls == []


def test_answer_has_citations_and_history_in_prompt():
    calls = []
    llm = make_fake_llm(answer="Twenty days [1].", calls=calls)
    chunks = [chunk("Twenty days of vacation.", document_id="1", source_name="a.pdf", page_number=2)]

    result = generate_answer("How many days?", llm, chunks, history=[("user", "hi"), ("assistant", "hello")])

    assert result.answer == "Twenty days [1]." and not result.abstained
    assert result.citations[0].marker == "[1]" and result.citations[0].page_number == 2
    assert "Twenty days of vacation." in calls[0]
    assert "Human: hi" in calls[0] and "AI: hello" in calls[0]


def test_model_abstaining_returns_no_citations():
    llm = make_fake_llm(answer="I don't have enough information to answer that.")
    chunks = [chunk("Unrelated text.", document_id="1", source_name="a.pdf")]
    result = generate_answer("What is the CEO's salary?", llm, chunks)
    assert result.abstained and result.citations == []


# --- importing the retrieval code must not touch Qdrant or load models -------------------


def test_importing_orchestrator_has_no_side_effects(monkeypatch):
    from app.ingestion.embedding import vector_store

    def forbidden(*args, **kwargs):
        raise AssertionError("vector store must not be built at import time")

    monkeypatch.setattr(vector_store, "get_vector_store", forbidden)
    monkeypatch.delitem(sys.modules, "app.retrieval.orchestrator", raising=False)

    module = importlib.import_module("app.retrieval.orchestrator")

    assert callable(module.get_search_store)


def test_reranker_model_is_loaded_once(monkeypatch):
    from app.retrieval import reranker

    loaded = []

    class FakeEncoder:
        def __init__(self, model_name, cache_dir=None):
            loaded.append((model_name, cache_dir))

    monkeypatch.setattr(reranker, "TextCrossEncoder", FakeEncoder)
    reranker.get_reranker.cache_clear()
    try:
        first = reranker.get_reranker("some-model")
        second = reranker.get_reranker("some-model")
    finally:
        reranker.get_reranker.cache_clear()

    assert first is second
    assert len(loaded) == 1
    assert loaded[0][0] == "some-model"
