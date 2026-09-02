# app/ingestion/embedding/vector_store.py

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, SparseVectorParams
from langchain_qdrant import QdrantVectorStore, RetrievalMode

from app.ingestion.embedding.embedders import build_dense_embedder, build_sparse_embedder
from app.ingestion.embedding.models import EmbeddingConfig

# BGE-M3 dense vector dimensionality — fixed by the model itself.
BGE_M3_DIM = 1024


def get_qdrant_client(config: EmbeddingConfig) -> QdrantClient:
    return QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)


def ensure_collection(client: QdrantClient, config: EmbeddingConfig) -> None:
    """
    Creates the collection with both a dense vector space (BGE-M3,
    cosine distance) and a named sparse vector space (BM25), if it
    doesn't already exist. Idempotent — safe to call on every startup.
    """
    if client.collection_exists(config.collection_name):
        return

    client.create_collection(
        collection_name=config.collection_name,
        vectors_config={
            "dense": VectorParams(size=BGE_M3_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(),
        },
    )


def get_vector_store(config: EmbeddingConfig) -> QdrantVectorStore:
    """
    Builds a hybrid QdrantVectorStore: dense (BGE-M3) + sparse (BM25),
    fused via RRF at query time. Collection is created here if absent.
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