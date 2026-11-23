# eval_code/ingest.py
"""
Step 1 of a codebase evaluation run: put the frozen source files into their OWN Qdrant collection using the real
ingestion pipeline (load -> chunk -> embed -> index), exactly what the Celery worker does for an uploaded code file.
Nothing here needs Postgres or Redis.
"""

import hashlib
from datetime import datetime, timezone

EVAL_USER_ID = 424242   # every eval chunk is "uploaded by" this fake user, so retrieval filters on it as in production

# Collections this harness must never reset: the real one, and the documents evaluation's.
PROTECTED_COLLECTIONS = {"documents", "knowledgeos_eval"}


def ingest_corpus(reset: bool = True) -> dict:
    from app.core.config import settings
    from app.ingestion.embedding.models import EmbeddingConfig
    from app.ingestion.embedding.vector_store import get_qdrant_client
    from app.ingestion.pipeline import ingest_file
    from eval_code.suite import build_corpus

    # Safety: an evaluation must never write into (or delete from) the real collection or the documents evaluation's.
    assert settings.qdrant_collection != "documents", "refusing to run the evaluation on the production collection"
    assert settings.qdrant_collection not in PROTECTED_COLLECTIONS, f"refusing to touch the collection {settings.qdrant_collection!r}"

    config = EmbeddingConfig()
    client = get_qdrant_client(config)
    if reset and client.collection_exists(config.collection_name):
        client.delete_collection(config.collection_name)

    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    chunks_per_file = {}
    for number, source in enumerate(build_corpus(), start=1):
        metadata = {
            "document_id": str(number),
            "uploaded_by": str(EVAL_USER_ID),
            "doc_type": source.kind,
            "mime_type": source.mime,
            "source_name": source.filename,
            "document_hash": hashlib.sha256(source.data).hexdigest(),
            "embedding_model": config.dense_model_name,
            "created_at": created_at,
        }
        result = ingest_file(source.data, source.filename, source.mime, metadata)
        if not result.success:
            raise RuntimeError(f"ingesting {source.filename} failed: {result.error}")
        chunks_per_file[source.filename] = result.num_chunks

    return {
        "collection": config.collection_name,
        "documents": len(chunks_per_file),
        "chunks": sum(chunks_per_file.values()),
        "chunks_per_document": chunks_per_file,
    }
