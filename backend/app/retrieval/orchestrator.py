# app/retrieval/orchestrator.py

import logging
from functools import lru_cache

from app.ingestion.embedding.models import EmbeddingConfig
from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator
from app.ingestion.embedding.vector_store import get_vector_store
from app.retrieval.model import RetrievalConfig, RetrievalResult
from app.retrieval.query_rewriter import build_query_rewriter
from app.retrieval.multi_query import build_multi_query_chain, generate_query_variants
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.merge import merge_and_truncate
from app.retrieval.reranker import get_reranker
from app.retrieval.parent_expander import ParentExpander
from app.retrieval.filters import build_qdrant_filter

logger = logging.getLogger(__name__)

parent_expander = ParentExpander()


@lru_cache(maxsize=1)
def get_search_store():
    """
    Connects to Qdrant and loads the embedding models the first time it is
    called, then reuses them. (Nothing heavy happens when this module is
    imported.)
    """
    return get_vector_store(EmbeddingConfig())


def rewrite_question(llm, question: str, history: str) -> str:
    """Turns a follow-up like "what about 2023?" into a standalone question."""
    if not history:
        return question  # first message, nothing to resolve

    try:
        rewritten = build_query_rewriter(llm).invoke({"question": question, "history": history})
    except Exception:
        logger.warning("Query rewriting failed, using the original question", exc_info=True)
        return question

    return rewritten.strip() or question


def make_query_variants(llm, query: str, num_variants: int) -> list[str]:
    """The query itself plus a few LLM paraphrases (no duplicates)."""
    try:
        variants = generate_query_variants(build_multi_query_chain(llm), query, num_variants)
    except Exception:
        logger.warning("Multi-query generation failed, using the single query", exc_info=True)
        return [query]

    return list(dict.fromkeys(variants))  # remove duplicates, keep order


def retrieve(
    question: str,
    user_id: int,
    llm=None,
    history: str = "",
    config: RetrievalConfig | None = None,
    doc_type: str | None = None,
    document_ids: list[str] | None = None,
) -> RetrievalResult:
    """
    Runs the full retrieval chain for one question:
    rewrite -> multi-query -> hybrid search (dense + BM25) -> merge -> rerank -> parent expansion.

    - user_id: results are ALWAYS limited to chunks this user uploaded.
    - llm: optional. Without it the question is searched as-is
      (no rewriting, no extra query variants).
    - history: recent conversation as plain text, used to rewrite follow-up questions.
    - document_ids: optionally search only inside these documents.
    """
    config = config or RetrievalConfig()

    # step 1 + 2: rewrite the question and make query variants (only if we have an LLM)
    rewritten_query = question
    variants = [question]
    if llm is not None:
        rewritten_query = rewrite_question(llm, question, history)
        variants = make_query_variants(llm, rewritten_query, config.num_query_variants)

    # step 3: hybrid search for each variant, always restricted to this user's chunks
    qdrant_filter = build_qdrant_filter(
        doc_type=doc_type,
        uploaded_by=str(user_id),
        document_ids=document_ids,
    )
    store = get_search_store()

    all_chunks = []
    for variant in variants:
        chunks = hybrid_search(
            store,
            query=variant,
            k=config.hybrid_search_k,
            qdrant_filter=qdrant_filter,
        )
        all_chunks.extend(chunks)

    # step 4: merge + dedupe + truncate
    candidates = merge_and_truncate(
        all_chunks,
        id_fn=EmbeddingOrchestrator._make_id,
        pool_size=config.candidate_pool_size,
    )

    # step 5: rerank with the cross-encoder
    reranker = get_reranker(config.reranker_model_name)
    top_chunks = reranker.rerank(rewritten_query, candidates, top_k=config.final_top_k)

    # step 6: expand to parent content if enabled
    if config.use_parent_expansion:
        top_chunks = parent_expander.expand(top_chunks)

    return RetrievalResult(
        original_query=question,
        rewritten_query=rewritten_query,
        query_variants=variants,
        chunks=top_chunks,
    )
