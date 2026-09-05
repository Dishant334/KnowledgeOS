# app/retrieval/orchestrator.py

import logging

from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator
from app.retrieval.model import RetrievalConfig, RetrievalResult
from app.retrieval.query_rewriter import build_query_rewriter
from app.retrieval.multi_query import build_multi_query_chain, generate_query_variants
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.merge import merge_and_truncate
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.parent_expander import ParentExpander
from app.retrieval.filters import build_qdrant_filter

logger = logging.getLogger(__name__)

# built once, reused across every call (loads the embedding model +
# reranker model once instead of on every request)
embedding_orchestrator = EmbeddingOrchestrator()
parent_expander = ParentExpander()


def retrieve(
    question: str,
    llm,
    config: RetrievalConfig = None,
    history: str = "",
    doc_type: str | None = None,
    uploaded_by: str | None = None,
) -> RetrievalResult:
  

    config = config or RetrievalConfig()

    # step 1: rewrite query
    rewriter = build_query_rewriter(llm)
    rewritten_query = rewriter.invoke({"question": question, "history": history})

    # step 2: generate variants
    multi_query_chain = build_multi_query_chain(llm)
    variants = generate_query_variants(multi_query_chain, rewritten_query, config.num_query_variants)

    # step 3: hybrid search each variant
    qdrant_filter = build_qdrant_filter(doc_type=doc_type, uploaded_by=uploaded_by)

    all_chunks = []
    for variant in variants:
        chunks = hybrid_search(
            embedding_orchestrator.vector_store,
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

    # step 5: rerank
    reranker = CrossEncoderReranker(config.reranker_model_name)
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