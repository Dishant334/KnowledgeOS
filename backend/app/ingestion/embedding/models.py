# app/ingestion/embedding/models.py

from dataclasses import dataclass, field
from app.core.config import settings


@dataclass
class EmbeddingConfig:
    qdrant_url: str = settings.qdrant_url
    qdrant_api_key: str | None = None
    collection_name: str = "documents"

    dense_model_name: str = "BAAI/bge-m3"
    sparse_model_name: str = "Qdrant/bm25"

    batch_size: int = 32

    # Phase 3 — payload fields that need a Qdrant index for filtered
    # search to be fast (not a full collection scan).
    indexed_payload_fields: tuple[str, ...] = field(
        default_factory=lambda: (
            "document_id",
            "uploaded_by",
            "doc_type",
            "embedding_model",
            "created_at",
        )
    )

    # Phase 3 — retry/backoff for transient Qdrant write failures.
    retry_attempts: int = 3
    retry_wait_min_seconds: float = 1.0
    retry_wait_max_seconds: float = 10.0