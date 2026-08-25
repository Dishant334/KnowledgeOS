from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    doc_type: Optional[str] = Field(
        default=None,
        description="Optional payload filter, e.g. 'pdf' or 'policy' (wired in once metadata filtering lands).",
   )


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: int
    chunk_text: str
    score: float
    source_name: Optional[str] = None
    page_number: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class RetrieveResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
    took_ms: float
