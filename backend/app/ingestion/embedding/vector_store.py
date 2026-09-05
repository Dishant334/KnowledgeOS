# app/ingestion/embedding/vector_store.py

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    PayloadSchemaType,
)
from langchain_qdrant import QdrantVectorStore, RetrievalMode

from app.ingestion.embedding.embedders import build_dense_embedder, build_sparse_embedder
from app.ingestion.embedding.models import EmbeddingConfig

# BGE-M3 dense vector dimensionality — fixed by the model itself.
BGE_M3_DIM = 1024

# Maps a payload field name to the Qdrant schema type it should be
# indexed as. created_at needs DATETIME so range filters (e.g. "docs
# uploaded in the last 30 days") work correctly; everything else here
# is an exact-match filter field, so KEYWORD is correct.
_PAYLOAD_FIELD_SCHEMAS: dict[str, PayloadSchemaType] = {
    "document_id": PayloadSchemaType.KEYWORD,
    "uploaded_by": PayloadSchemaType.KEYWORD,
    "doc_type": PayloadSchemaType.KEYWORD,
    "embedding_model": PayloadSchemaType.KEYWORD,
    "created_at": PayloadSchemaType.DATETIME,
}


def get_qdrant_client(config: EmbeddingConfig) -> QdrantClient:
    return QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)


def ensure_collection(client: QdrantClient, config: EmbeddingConfig) -> None:
    """
    Creates the collection with both a dense vector space (BGE-M3,
    cosine distance) and a named sparse vector space (BM25), if it
    doesn't already exist. Idempotent — safe to call on every startup.
    """
    if not client.collection_exists(config.collection_name):
        client.create_collection(
            collection_name=config.collection_name,
            vectors_config={
                "dense": VectorParams(size=BGE_M3_DIM, distance=Distance.COSINE),
            },
            sparse_vectors_config={
                "sparse": SparseVectorParams(),
            },
        )

    # Phase 3: ensure payload indexes exist regardless of whether the
    # collection was just created or already existed — covers the case
    # where the collection was created before indexing was added.
    ensure_payload_indexes(client, config)


def ensure_payload_indexes(client: QdrantClient, config: EmbeddingConfig) -> None:
    """
    Creates a payload index for every field in
    config.indexed_payload_fields, skipping any that are already
    indexed. Idempotent and safe to call on every startup — Qdrant
    would otherwise error on a duplicate index name.
    """
    collection_info = client.get_collection(config.collection_name)
    already_indexed = set(collection_info.payload_schema.keys())

    for field_name in config.indexed_payload_fields:
        if field_name in already_indexed:
            continue

        schema_type = _PAYLOAD_FIELD_SCHEMAS.get(field_name, PayloadSchemaType.KEYWORD)

        client.create_payload_index(
            collection_name=config.collection_name,
            field_name=field_name,
            field_schema=schema_type,
        )


def get_vector_store(config: EmbeddingConfig) -> QdrantVectorStore:
    """
    Builds a hybrid QdrantVectorStore: dense (BGE-M3) + sparse (BM25),
    fused via RRF at query time. Collection and payload indexes are
    created here if absent.
    """
    client = get_qdrant_client(config)
    ensure_collection(client, config)

    return QdrantVectorStore(
        client=client,
        collection_name=config.collection_name,
        embedding=build_dense_embedder(config),
        sparse_embedding=build_sparse_embedder(config),
        retrieval_mode=RetrievalMode.HYBRID,
        vector_name="dense",
        sparse_vector_name="sparse",
    )