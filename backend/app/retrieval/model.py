# app/retrieval/models.py

from dataclasses import dataclass, field
from langchain_core.documents import Document


@dataclass
class RetrievalConfig:
    # LLM paraphrases of the question, each searched separately. OFF by default (decided 2026-11-09): measured on the
    # 45-question eval, 4 paraphrases found the needed passage as often (Hit@5 0.93 vs 0.93) but made retrieval
    # ~7 s slower locally (9.9 s vs 2.9 s p50). The history-aware rewrite of the question still runs.
    num_query_variants: int = 0
    hybrid_search_k: int = 15          # per-variant, before merge
    candidate_pool_size: int = 30      # after merge/dedupe, before rerank
    final_top_k: int = 5               # after rerank
    reranker_model_name: str = "BAAI/bge-reranker-base"


@dataclass
class ScoredChunk:
    document: Document
    fused_score: float | None = None       # Qdrant's server-side RRF output
    rerank_score: float | None = None
    query_variant: str | None = None


@dataclass
class RetrievalResult:
    original_query: str
    rewritten_query: str
    query_variants: list[str] = field(default_factory=list)
    chunks: list[ScoredChunk] = field(default_factory=list)