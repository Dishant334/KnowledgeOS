#Merge top 20-50 candidate using dedup/union

# app/retrieval/merge.py

from app.retrieval.model import ScoredChunk


def merge_and_truncate(
    all_scored_chunks: list[ScoredChunk],
    id_fn,
    pool_size: int,
) -> list[ScoredChunk]:
    """
    Merges chunks retrieved across multiple query variants:
      1. dedupe by chunk ID (same deterministic ID scheme as
         EmbeddingOrchestrator._make_id)
      2. if a chunk appears under multiple variants, keep its BEST
         fused_score rather than the first one seen — a chunk that
         scored well under more than one phrasing is a stronger
         candidate, not a weaker one
      3. sort by fused_score, truncate to pool_size
    """
    best_by_id: dict[str, ScoredChunk] = {}

    for scored_chunk in all_scored_chunks:
        chunk_id = id_fn(scored_chunk.document)
        existing = best_by_id.get(chunk_id)

        if existing is None or (scored_chunk.fused_score or 0) > (existing.fused_score or 0):
            best_by_id[chunk_id] = scored_chunk

    merged = sorted(best_by_id.values(), key=lambda sc: sc.fused_score or 0, reverse=True)
    return merged[:pool_size]