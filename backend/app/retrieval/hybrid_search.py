# app/retrieval/hybrid_search.py

from app.retrieval.model import ScoredChunk


def hybrid_search(vector_store, query: str, k: int, qdrant_filter=None) -> list[ScoredChunk]:
    """
    One query variant's hybrid search: dense (BGE-M3) + sparse (BM25),
    fused server-side via Qdrant's native RRF 
    """
    results = vector_store.similarity_search_with_score(query, k=k, filter=qdrant_filter)
    return [
        ScoredChunk(document=doc, fused_score=score, query_variant=query)
        for doc, score in results
    ]