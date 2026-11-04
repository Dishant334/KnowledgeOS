import logging
import time

from fastapi import HTTPException
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator
from app.retrieval.model import RetrievalConfig, RetrievalResult, ScoredChunk
from app.retrieval.orchestrator import retrieve
from app.schemas.retrieve import RetrieveRequest, RetrieveResponse, RetrievedChunk

logger = logging.getLogger(__name__)

# Errors that mean "Qdrant can't be reached / answered badly" (not a bug in our code)
SEARCH_UNAVAILABLE_ERRORS = (ConnectionError, TimeoutError, ResponseHandlingException, UnexpectedResponse)


def run_retrieval(
    question: str,
    user_id: int,
    llm=None,
    history: str = "",
    top_k: int = 5,
    doc_type: str | None = None,
    document_ids: list[int] | None = None,
) -> RetrievalResult:
    """Runs the retrieval pipeline; turns Qdrant outages into a 503."""
    config = RetrievalConfig(final_top_k=top_k, candidate_pool_size=max(30, top_k))

    try:
        return retrieve(
            question,
            user_id=user_id,
            llm=llm,
            history=history,
            retrieval_config=config,
            doc_type=doc_type,
            # payload ids are strings
            document_ids=[str(i) for i in document_ids] if document_ids else None,
        )
    except SEARCH_UNAVAILABLE_ERRORS:
        logger.exception("Search backend unavailable")
        raise HTTPException(status_code=503, detail="Search is temporarily unavailable, please try again")


def to_retrieved_chunk(scored_chunk: ScoredChunk) -> RetrievedChunk:
    metadata = scored_chunk.document.metadata
    score = scored_chunk.rerank_score if scored_chunk.rerank_score is not None else scored_chunk.fused_score

    return RetrievedChunk(
        chunk_id=EmbeddingOrchestrator._make_id(scored_chunk.document),
        document_id=int(metadata["document_id"]),
        chunk_text=scored_chunk.document.page_content,
        score=score or 0.0,
        fused_score=scored_chunk.fused_score,
        rerank_score=scored_chunk.rerank_score,
        source_name=metadata.get("source_name", metadata.get("source")),
        page_number=metadata.get("page_number"),
    )


def retrieve_chunks(request: RetrieveRequest, user_id: int, llm=None) -> RetrieveResponse:
    """Backs POST /retrieve: the ranked chunks (with per-stage scores) for a query."""
    start = time.perf_counter()

    result = run_retrieval(
        request.query,
        user_id=user_id,
        llm=llm,
        top_k=request.top_k,
        doc_type=request.doc_type,
        document_ids=request.document_ids,
    )

    results = [to_retrieved_chunk(chunk) for chunk in result.chunks]
    took_ms = (time.perf_counter() - start) * 1000
    return RetrieveResponse(query=request.query, results=results, took_ms=took_ms)
