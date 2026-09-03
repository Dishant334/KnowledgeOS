# app/ingestion/embedding/models.py

from dataclasses import dataclass
from app.core.config import settings


@dataclass
class EmbeddingConfig:
    qdrant_url: str = settings.qdrant_url
    qdrant_api_key: str | None = None
    collection_name: str = "documents"

    dense_model_name: str = "BAAI/bge-m3"
    sparse_model_name: str = "Qdrant/bm25"

    batch_size: int = 32