# app/retrieval/reranker.py

from functools import lru_cache

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.core.config import settings
from app.retrieval.model import ScoredChunk


class CrossEncoderReranker:
    """
    Reranks a candidate set of chunks against the query using a
    cross-encoder (bge-reranker, run locally via fastembed — same
    "free, local" reasoning as the BGE embedder choice).

    Cross-encoders score (query, document) pairs jointly, which is
    slower per-pair than the bi-encoder similarity search that
    produced the candidate set, but far more precise — this is why
    it runs AFTER hybrid search narrows the corpus down to a small
    candidate set, not over the whole collection.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self._model = TextCrossEncoder(
            model_name=model_name,
            cache_dir=settings.fastembed_cache_path,
        )

    def rerank(self, query: str, scored_chunks: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        if not scored_chunks:
            return []

        documents = [sc.document.page_content for sc in scored_chunks]
        scores = list(self._model.rerank(query, documents))

        for scored_chunk, score in zip(scored_chunks, scores):
            scored_chunk.rerank_score = float(score)

        scored_chunks.sort(key=lambda sc: sc.rerank_score, reverse=True)
        return scored_chunks[:top_k]


@lru_cache(maxsize=2)
def get_reranker(model_name: str) -> CrossEncoderReranker:
    """Loads the model the first time it is needed, then reuses it."""
    return CrossEncoderReranker(model_name)
