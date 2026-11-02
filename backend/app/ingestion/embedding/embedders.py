# app/ingestion/embedding/embedders.py

from fastembed import TextEmbedding, SparseTextEmbedding #Actual embedings
from langchain_core.embeddings import Embeddings
from langchain_qdrant import SparseEmbeddings #for data format
from langchain_qdrant.sparse_embeddings import SparseVector  #for data format 

from app.ingestion.embedding.models import EmbeddingConfig


class BGEM3DenseEmbedder(Embeddings):
    """
    Dense embedder wrapping fastembed's BGE (bge-large-en-v1.5) model directly (not via
    LangChain's prebuilt FastEmbedEmbeddings), so we control:
      - the query instruction BGE v1.5 recommends for search queries
        (improves retrieval accuracy vs. no prefix)
      - batch size passed straight to fastembed's ONNX inference

    Implements LangChain's Embeddings interface so it plugs directly
    into QdrantVectorStore (or any other LangChain vector store)
    without any adapter code.
    """

    # BGE v1.5's recommended instruction for short query -> passage retrieval
    # (fastembed does not add it). Applied to queries only.
    # Document-side embeddings use no prefix. This asymmetry is exactly
    # what the prebuilt LangChain wrapper doesn't let you control.
    QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model = TextEmbedding(model_name=config.dense_model_name, cache_dir=config.cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.embed(texts, batch_size=self.config.batch_size)
        return [vector.tolist() for vector in embeddings]

    def embed_query(self, text: str) -> list[float]:
        prefixed = f"{self.QUERY_PREFIX}{text}"
        embeddings = list(self._model.embed([prefixed]))
        return embeddings[0].tolist()


class BM25SparseEmbedder(SparseEmbeddings):
    """
    Sparse (BM25) embedder wrapping fastembed's BM25 model directly
    (not via LangChain's prebuilt FastEmbedSparse), for the same
    reason — direct control over batch size and how output maps to
    Qdrant's SparseVector shape, without depending on the wrapper's
    internal assumptions.

    Implements langchain_qdrant's SparseEmbeddings interface, which
    QdrantVectorStore expects for the sparse_embedding argument.
    """

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model = SparseTextEmbedding(model_name=config.sparse_model_name, cache_dir=config.cache_dir)

    def embed_documents(self, texts: list[str]) -> list[SparseVector]:
        results = self._model.embed(texts, batch_size=self.config.batch_size)
        return [
            SparseVector(indices=r.indices.tolist(), values=r.values.tolist())
            for r in results
        ]

    def embed_query(self, text: str) -> SparseVector:
        # query_embed (not embed): BM25's TF saturation / length normalization
        # belongs on the document side only. The query side marks each term as
        # present (weight 1); Qdrant applies IDF (modifier=IDF).
        result = next(iter(self._model.query_embed(text)))
        return SparseVector(
            indices=result.indices.tolist(),
            values=[float(v) for v in result.values.tolist()],
        )


def build_dense_embedder(config: EmbeddingConfig) -> BGEM3DenseEmbedder:
    return BGEM3DenseEmbedder(config)


def build_sparse_embedder(config: EmbeddingConfig) -> BM25SparseEmbedder:
    return BM25SparseEmbedder(config)