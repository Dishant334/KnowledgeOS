# app/ingestion/models.py

from dataclasses import dataclass, field


@dataclass
class IngestionResult:
    filename: str
    success: bool
    num_documents: int = 0
    num_chunks: int = 0
    point_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None