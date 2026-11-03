"""
Retrieval — INTEGRATION tests with REAL components:
bge-large dense model, BM25 sparse model, bge-reranker cross-encoder, and
Qdrant (isolated collection `knowledgeos_test_chunks`). The corpus is in
tests/conftest.py (CORPUS). LLM steps use a fake model (no real LLM exists yet).

Skipped automatically if Qdrant or the models are unavailable.
"""

import pytest
from langchain_qdrant import QdrantVectorStore, RetrievalMode

from app.ingestion.embedding.embedders import build_dense_embedder, build_sparse_embedder
from app.ingestion.embedding.vector_store import get_qdrant_client
from app.retrieval.filters import build_qdrant_filter
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.model import RetrievalConfig
from app.retrieval.orchestrator import get_search_store, retrieve
from app.retrieval.reranker import get_reranker
from tests.conftest import make_fake_llm

USER_1 = 1
USER_2 = 2


def stores(config, mode):
    """A vector store on the test collection that searches in ONE mode only."""
    kwargs = {
        RetrievalMode.DENSE: {"embedding": build_dense_embedder(config)},
        RetrievalMode.SPARSE: {"sparse_embedding": build_sparse_embedder(config)},
    }[mode]
    return QdrantVectorStore(
        client=get_qdrant_client(config),
        collection_name=config.collection_name,
        retrieval_mode=mode,
        vector_name="dense",
        sparse_vector_name="sparse",
        **kwargs,
    )


def texts(results):
    return [doc.page_content for doc, _ in results]


def user_filter(user_id, **kwargs):
    return build_qdrant_filter(uploaded_by=str(user_id), **kwargs)


# --- dense -----------------------------------------------------------------------------


def test_dense_finds_paraphrase_without_shared_keywords(retrieval_corpus):
    store = stores(retrieval_corpus, RetrievalMode.DENSE)
    results = store.similarity_search_with_score(
        "How much holiday time do staff get each year?", k=3, filter=user_filter(USER_1)
    )
    assert "twenty days of paid vacation" in texts(results)[0]


# --- sparse (BM25) -----------------------------------------------------------------------


def test_sparse_finds_rare_exact_keyword(retrieval_corpus):
    store = stores(retrieval_corpus, RetrievalMode.SPARSE)
    results = store.similarity_search_with_score("Zephyrwood", k=3, filter=user_filter(USER_1))
    assert texts(results) == ["Project Zephyrwood launches in the spring."]


def test_sparse_does_not_match_paraphrase(retrieval_corpus):
    """BM25 needs shared words: this is why dense search is combined with it."""
    store = stores(retrieval_corpus, RetrievalMode.SPARSE)
    # no word (or word stem) in common with the vacation chunk
    results = store.similarity_search_with_score("holiday entitlement", k=3, filter=user_filter(USER_1))
    assert results == []


# --- hybrid (dense + BM25, fused by Qdrant with RRF) ----------------------------------------


def test_hybrid_finds_what_only_dense_finds(retrieval_corpus):
    results = hybrid_search(get_search_store(), "How much holiday time do staff get each year?", k=3,
                            qdrant_filter=user_filter(USER_1))
    assert "twenty days of paid vacation" in results[0].document.page_content


def test_hybrid_finds_what_only_sparse_finds(retrieval_corpus):
    results = hybrid_search(get_search_store(), "Zephyrwood", k=5, qdrant_filter=user_filter(USER_1))
    assert results[0].document.page_content == "Project Zephyrwood launches in the spring."


def test_hybrid_results_come_from_dense_and_sparse_and_are_fused(retrieval_corpus):
    query = "paid vacation days"
    flt = user_filter(USER_1)
    dense = texts(stores(retrieval_corpus, RetrievalMode.DENSE).similarity_search_with_score(query, k=3, filter=flt))
    sparse = texts(stores(retrieval_corpus, RetrievalMode.SPARSE).similarity_search_with_score(query, k=3, filter=flt))
    hybrid = hybrid_search(get_search_store(), query, k=3, qdrant_filter=flt)

    hybrid_texts = [h.document.page_content for h in hybrid]
    assert set(hybrid_texts) <= set(dense) | set(sparse)
    # ranked first by BOTH lists -> ranked first after fusion
    assert dense[0] == sparse[0] == hybrid_texts[0]
    scores = [h.fused_score for h in hybrid]
    assert all(score is not None for score in scores)
    assert scores == sorted(scores, reverse=True)


# --- isolation (strict per-user) -------------------------------------------------------------


def test_hybrid_search_with_user_filter_never_returns_other_users_chunks(retrieval_corpus):
    for user_id in (USER_1, USER_2):
        results = hybrid_search(get_search_store(), "Berlin office vacation cafeteria lunch", k=10,
                                qdrant_filter=user_filter(user_id))
        assert results
        assert all(r.document.metadata["uploaded_by"] == str(user_id) for r in results)


def test_retrieve_is_limited_to_the_calling_user(retrieval_corpus):
    result = retrieve("Berlin office salary bands", user_id=USER_1)
    assert result.chunks
    assert all(c.document.metadata["uploaded_by"] == "1" for c in result.chunks)
    assert all("Berlin" not in c.document.page_content for c in result.chunks)


def test_user_without_documents_gets_nothing(retrieval_corpus):
    assert retrieve("vacation", user_id=999).chunks == []


def test_document_ids_filter_cannot_reach_other_users_documents(retrieval_corpus):
    ok = retrieve("work", user_id=USER_1, document_ids=["11"])
    assert {c.document.metadata["document_id"] for c in ok.chunks} == {"11"}
    stolen = retrieve("vacation", user_id=USER_1, document_ids=["20"])   # document 20 belongs to user 2
    assert stolen.chunks == []


def test_doc_type_filter(retrieval_corpus):
    result = retrieve("work from home", user_id=USER_1, doc_type="md")
    assert result.chunks and all(c.document.metadata["doc_type"] == "md" for c in result.chunks)


# --- reranker --------------------------------------------------------------------------------------


def test_cross_encoder_reorders_and_scores(retrieval_corpus):
    from langchain_core.documents import Document

    from app.retrieval.model import RetrievalConfig, ScoredChunk

    reranker = get_reranker(RetrievalConfig().reranker_model_name)
    candidates = [
        ScoredChunk(Document(page_content="The cafeteria serves lunch at noon."), fused_score=0.9),
        ScoredChunk(Document(page_content="Employees get twenty days of paid vacation."), fused_score=0.1),
    ]
    top = reranker.rerank("How many vacation days do employees get?", candidates, top_k=1)

    assert len(top) == 1
    assert "vacation" in top[0].document.page_content
    # fused scores said the cafeteria chunk was better; the cross-encoder disagrees
    scores = {c.document.page_content: c.rerank_score for c in candidates}
    assert scores["Employees get twenty days of paid vacation."] > scores["The cafeteria serves lunch at noon."]


def test_reranker_is_cached(retrieval_corpus):
    name = RetrievalConfig().reranker_model_name
    assert get_reranker(name) is get_reranker(name)


# --- the whole chain ------------------------------------------------------------------------------------


def test_retrieve_without_llm_searches_the_question_as_is(retrieval_corpus):
    result = retrieve("How many vacation days do employees get?", user_id=USER_1,
                      config=RetrievalConfig(final_top_k=3))
    assert result.rewritten_query == result.original_query
    assert result.query_variants == [result.original_query]
    assert "twenty days of paid vacation" in result.chunks[0].document.page_content
    assert len(result.chunks) <= 3
    for c in result.chunks:
        assert c.fused_score is not None and c.rerank_score is not None
    scores = [c.rerank_score for c in result.chunks]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_with_llm_rewrites_followups_and_uses_variants(retrieval_corpus):
    calls = []
    llm = make_fake_llm(
        rewritten="How many vacation days do employees get?",
        variants=["paid vacation days", "annual leave allowance"],
        calls=calls,
    )
    result = retrieve("and for employees?", user_id=USER_1, llm=llm,
                      history="User: Tell me about leave.\nAssistant: We have a leave policy.")

    assert result.rewritten_query == "How many vacation days do employees get?"
    assert result.query_variants == [result.rewritten_query, "paid vacation days", "annual leave allowance"]
    assert "twenty days of paid vacation" in result.chunks[0].document.page_content
    assert any("Tell me about leave" in prompt for prompt in calls)   # history reached the rewriter


def test_retrieve_survives_a_broken_llm(retrieval_corpus):
    from langchain_core.runnables import RunnableLambda

    def fail(prompt_value):
        raise RuntimeError("llm is down")

    result = retrieve("How many vacation days do employees get?", user_id=USER_1, llm=RunnableLambda(fail),
                      history="User: hi")
    assert result.query_variants == ["How many vacation days do employees get?"]
    assert "twenty days of paid vacation" in result.chunks[0].document.page_content


def test_parent_expansion_returns_the_full_section(retrieval_corpus):
    """Chunks that have parent_content (PDF/DOCX prose) come back as the whole parent section."""
    from langchain_core.documents import Document

    from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator

    EmbeddingOrchestrator(retrieval_corpus).embed_and_index([
        Document(page_content="Parking permits cost forty dollars.", metadata={
            "document_id": "30", "uploaded_by": "1", "doc_type": "pdf", "source_name": "park.pdf",
            "source": "park.pdf", "chunk_index": 0, "parent_id": "park.pdf_p0",
            "parent_content": "PARKING SECTION. Parking permits cost forty dollars. Apply at the front desk.",
        })
    ])
    result = retrieve("How much is a parking permit?", user_id=USER_1)
    top = result.chunks[0]
    assert top.expanded
    assert top.document.page_content.startswith("PARKING SECTION.")
