# app/ingestion/chunking/orchestrator.py

import logging
from typing import Optional

from langchain_core.documents import Document

from app.ingestion.chunking.model import ChunkingConfig
from app.ingestion.chunking.splitter import get_strategy_for_mime_type

logger = logging.getLogger(__name__)


class ChunkingOrchestrator:
    """
    Selects the right ChunkingStrategy for a document's MIME type via
    the registry, runs it, and attaches consistent chunk-level
    metadata (chunk_index, total_chunks) regardless of which
    strategy produced the split.
    """

    def __init__(self, config: Optional[ChunkingConfig] = None):
        self.config = config or ChunkingConfig()

    def chunk_batch(self, documents: list[Document], mime_type: str) -> list[Document]:
        """
        Chunks all pages/slides/rows of ONE source (all sharing the
        same mime_type) using the strategy registered for that type.
        Uses split_batch so cross-document strategies (TableChunkingStrategy)
        work correctly — for other strategies this just flattens
        split() per document (see ChunkingStrategy.split_batch default).
        """
        if not documents:
            return []

        strategy = get_strategy_for_mime_type(mime_type, self.config)
        chunks = strategy.split_batch(documents)
        return self._attach_metadata(chunks)

    @staticmethod
    def _attach_metadata(chunks: list[Document]) -> list[Document]:
        total = len(chunks)
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["total_chunks"] = total
        return chunks