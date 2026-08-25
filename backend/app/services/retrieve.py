import time

from app.schemas.retrieve import RetrieveRequest, RetrieveResponse


def retrieve_chunks(request: RetrieveRequest, user_id: int) -> RetrieveResponse:
    """
    Stub retrieval service.

    Locks the typed request/response contract for `/retrieve` before the
    real hybrid retrieval pipeline (Qdrant dense search + BM25 fusion +
    cross-encoder rerank, Phase 3/4) exists. Always returns an empty
    result set for now -- no vector store is wired up yet.

    `user_id` is accepted (and unused) so single-tier data isolation /
    per-user filtering can be added here without changing the signature.
    """
    start = time.perf_counter()

    results: list = []

    took_ms = (time.perf_counter() - start) * 1000
    return RetrieveResponse(query=request.query, results=results, took_ms=took_ms)