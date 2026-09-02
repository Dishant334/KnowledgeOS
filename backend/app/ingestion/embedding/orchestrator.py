# app/ingestion/embedding/orchestrator.py

import logging
from typing import Optional
from uuid import  NAMESPACE_URL, uuid5

from langchain_core.documents import Document

from app.ingestion.embedding.models import EmbeddingConfig
from app.ingestion.embedding.vector_store import get_vector_store


logger = logging.getLogger(__name__)


class EmbeddingOrchestrator:
    """
    Coordinates embedding and indexing of document chunks.

    Responsibilities:
      1. Generate deterministic IDs.
      2. Process chunks in application-level batches.
      3. Send chunks to the Qdrant vector store.
    """

    def __init__(
        self,
        config: Optional[EmbeddingConfig] = None,
    ):
        self.config = config or EmbeddingConfig()

        self.vector_store = get_vector_store(
            self.config
        )

    def embed_and_index(
        self,
        chunks: list[Document],
    ) -> list[str]:
        """
        Embed and index all chunks.

        Qdrant/LangChain internally calls:

            dense embedder → BGE-M3
            sparse embedder → BM25

        Returns the IDs written to Qdrant.
        """

        if not chunks:
            return []

        ids = [
            self._make_id(chunk)
            for chunk in chunks
        ]

        source = chunks[0].metadata.get(
            "source",
            "unknown",
        )

        logger.info(
            "Indexing %d chunks into collection '%s' "
            "(source=%s)",
            len(chunks),
            self.config.collection_name,
            source,
        )

        written_ids: list[str] = []

        # Application-level batching.
        for start in range(
            0,
            len(chunks),
            self.config.batch_size,
        ):
            batch_chunks = chunks[
                start:start + self.config.batch_size
            ]

            batch_ids = ids[
                start:start + self.config.batch_size
            ]

            self.vector_store.add_documents(
                documents=batch_chunks,
                ids=batch_ids,
            )

            written_ids.extend(batch_ids)

        return written_ids

    @staticmethod
    def _make_id(
        chunk: Document,
    ) -> str:
        """
        Generate a deterministic UUID for a chunk.

        Same source + same location + same chunk index
        produces the same UUID.
        """

        source = str(
            chunk.metadata.get(
                "source",
                "unknown",
            )
        )

        chunk_index = str(
            chunk.metadata.get(
                "chunk_index",
                0,
            )
        )

        page = str(
            chunk.metadata.get(
                "page_number",
                "",
            )
            or chunk.metadata.get(
                "slide_number",
                "",
            )
            or ""
        )

        key = (
            f"{source}:"
            f"{page}:"
            f"{chunk_index}"
        )

        return str(
            uuid5(
                NAMESPACE_URL,
                key,
            )
        )