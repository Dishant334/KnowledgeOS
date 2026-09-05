# app/retrieval/models.py

from dataclasses import dataclass, field
from langchain_core.documents import Document


@dataclass
class RetrievalConfig:
    num_query_variants: int = 4
    hybrid_search_k: int = 15          # per-variant, before merge
    candidate_pool_size: int = 30      # after merge/dedupe, before rerank
    final_top_k: int = 5               # after rerank
    reranker_model_name: str = "BAAI/bge-reranker-base"
    use_parent_expansion: bool = True  # toggle for ablation in Phase 6 eval


@dataclass
class ScoredChunk:
    document: Document
    fused_score: float | None = None       # Qdrant's server-side RRF output
    rerank_score: float | None = None
    query_variant: str | None = None
    expanded: bool = False                 # True once parent_content has replaced page_content


@dataclass
class RetrievalResult:
    original_query: str
    rewritten_query: str
    query_variants: list[str] = field(default_factory=list)
    chunks: list[ScoredChunk] = field(default_factory=list)