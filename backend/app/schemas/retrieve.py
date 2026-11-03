from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    doc_type: Optional[str] = Field(
        default=None,
        description="Only search documents of this type, e.g. 'pdf', 'docx', 'md'.",
    )
    document_ids: Optional[list[int]] = Field(
        default=None,
        max_length=50,
        description="Only search inside these documents (your own documents only).",
    )


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: int
    chunk_text: str
    score: float                           # rerank score (falls back to fused score)
    fused_score: Optional[float] = None    # Qdrant hybrid (dense + BM25, RRF) score
    rerank_score: Optional[float] = None   # cross-encoder score
    source_name: Optional[str] = None
    page_number: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class RetrieveResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
    took_ms: float
