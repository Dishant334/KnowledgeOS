# app/ingestion/chunking/base.py

from abc import ABC, abstractmethod

from langchain_core.documents import Document


class ChunkingStrategy(ABC):
    """
    Interface every chunking strategy implements.

    split(document) handles the common case: one input Document ->
    many output chunk Documents.

    split_batch(documents) handles strategies that need to operate
    ACROSS multiple input documents at once (currently only
    TableChunkingStrategy, which groups rows spanning several
    row-level Documents into one chunk). Default implementation just
    calls split() on each document and flattens — override only when
    cross-document grouping is required.

    Metadata like chunk_index/total_chunks is attached centrally by
    ChunkingOrchestrator, not by strategies themselves.
    """

    @abstractmethod
    def split(self, document: Document) -> list[Document]:
        raise NotImplementedError

    def split_batch(self, documents: list[Document]) -> list[Document]:
        chunks: list[Document] = []
        for document in documents:
            chunks.extend(self.split(document))
        return chunks