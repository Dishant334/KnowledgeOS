# eval/ingest.py
"""
Step 1 of an evaluation run: put the evaluation corpus into its OWN Qdrant collection
using the real ingestion pipeline (load -> OCR -> clean -> chunk -> embed -> index), exactly
what the Celery worker does for an uploaded file. Nothing here needs Postgres or Redis.
"""

import hashlib
from datetime import datetime, timezone

EVAL_USER_ID = 424242   # every eval chunk is "uploaded by" this fake user, so retrieval filters on it as in production


def ingest_corpus(reset: bool = True) -> dict:
    from app.core.config import settings
    from app.ingestion.embedding.models import EmbeddingConfig
    from app.ingestion.embedding.vector_store import get_qdrant_client
    from app.ingestion.pipeline import ingest_file
    from eval.corpus import build_corpus

    # Safety: an evaluation must never write into (or delete from) the real collection.
    assert settings.qdrant_collection != "documents", "refusing to run the evaluation on the production collection"

    config = EmbeddingConfig()
    client = get_qdrant_client(config)
    if reset and client.collection_exists(config.collection_name):
        client.delete_collection(config.collection_name)

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    chunks_per_document = {}
    for number, document in enumerate(build_corpus(), start=1):
        metadata = {
            "document_id": str(number),
            "uploaded_by": str(EVAL_USER_ID),
            "doc_type": document.kind,
            "mime_type": document.mime,
            "source_name": document.filename,
            "document_hash": hashlib.sha256(document.data).hexdigest(),
            "embedding_model": config.dense_model_name,
            "created_at": created_at,
        }
        result = ingest_file(document.data, document.filename, document.mime, metadata)
        if not result.success:
            raise RuntimeError(f"ingesting {document.filename} failed: {result.error}")
        chunks_per_document[document.filename] = result.num_chunks

    return {
        "collection": config.collection_name,
        "documents": len(chunks_per_document),
        "chunks": sum(chunks_per_document.values()),
        "chunks_per_document": chunks_per_document,
    }
