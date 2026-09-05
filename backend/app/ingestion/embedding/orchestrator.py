# app/ingestion/embedding/orchestrator.py

import logging
from typing import Optional
from uuid import NAMESPACE_URL, uuid5

from langchain_core.documents import Document
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.ingestion.embedding.models import EmbeddingConfig
from app.ingestion.embedding.vector_store import get_vector_store


logger = logging.getLogger(__name__)


class EmbeddingOrchestrator:
    """
    Coordinates embedding and indexing of document chunks.

    Responsibilities:
      1. Generate deterministic IDs.
      2. Process chunks in application-level batches.
      3. Send chunks to the Qdrant vector store, with retry on
         transient write failures (Phase 3).
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

            self._add_documents_with_retry(
                batch_chunks,
                batch_ids,
            )

            written_ids.extend(batch_ids)

        return written_ids

    def _add_documents_with_retry(
        self,
        documents: list[Document],
        ids: list[str],
    ) -> None:
        """
        Wraps the actual Qdrant write with retry/backoff. Built as an
        instance method (not a decorated free function) so
        self.config.retry_attempts etc. are respected per-instance,
        rather than hardcoded at decoration time.
        """

        retrying_add = retry(
            stop=stop_after_attempt(self.config.retry_attempts),
            wait=wait_exponential(
                multiplier=1,
                min=self.config.retry_wait_min_seconds,
                max=self.config.retry_wait_max_seconds,
            ),
            # Only retry transient/connection-level failures. A
            # malformed vector shape or bad payload would fail
            # identically on retry — those exceptions are NOT caught
            # here and raise immediately, so a real bug isn't hidden
            # behind three wasted retry attempts.
            retry=retry_if_exception_type(
                (ResponseHandlingException, UnexpectedResponse, ConnectionError)
            ),
            reraise=True,
        )(self._add_documents)

        retrying_add(documents, ids)

    def _add_documents(
        self,
        documents: list[Document],
        ids: list[str],
    ) -> None:
        self.vector_store.add_documents(
            documents=documents,
            ids=ids,
        )

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