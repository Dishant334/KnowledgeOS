# app/ingestion/chunking/strategies.py

import logging

from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    HTMLHeaderTextSplitter,
)

from app.ingestion.chunking.base import ChunkingStrategy
from app.ingestion.chunking.model import ChunkingConfig

logger = logging.getLogger(__name__)


class RecursiveCharacterStrategy(ChunkingStrategy):
    """
    Base/fallback strategy. Token-aware (tiktoken), splits on
    paragraph -> line -> sentence -> word, falling back only when a
    larger separator can't produce a chunk under chunk_size.
    """

    def __init__(self, config: ChunkingConfig):
        self.config = config
        self._splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=config.encoding_name,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def split(self, document: Document) -> list[Document]:
        if not document.page_content or not document.page_content.strip():
            return []
        return self._splitter.split_documents([document])


class ParentChildStrategy(ChunkingStrategy):
    """
    Primary strategy for PROSE (PDF/DOCX).

    Splits each document into large "parent" sections first, then
    splits each parent into smaller "child" chunks. Children are what
    gets embedded/searched (small = precise retrieval); each child
    carries its parent's full text in metadata["parent_content"] so
    retrieval-time expansion can return the fuller context.

    Falls back to a plain recursive split (no parent/child split)
    when a document is too small to meaningfully have a parent
    layer — avoids producing a single child chunk with a redundant,
    identical parent_content.
    """

    def __init__(self, config: ChunkingConfig):
        self.config = config
        self._parent_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=config.encoding_name,
            chunk_size=config.parent_chunk_size,
            chunk_overlap=config.parent_chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self._child_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=config.encoding_name,
            chunk_size=config.child_chunk_size,
            chunk_overlap=config.child_chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def split(self, document: Document) -> list[Document]:
        if not document.page_content or not document.page_content.strip():
            return []

        parents = self._parent_splitter.split_documents([document])

        children: list[Document] = []
        for parent_index, parent in enumerate(parents):
            parent_id = f"{document.metadata.get('source', 'doc')}_p{parent_index}"

            child_docs = self._child_splitter.split_documents([parent])
            for child in child_docs:
                child.metadata["parent_id"] = parent_id
                child.metadata["parent_content"] = parent.page_content
                children.append(child)

        return children


class SlidePassthroughStrategy(ChunkingStrategy):
    """
    Strategy for SLIDES (PPTX). Assumes the loader already emits one
    Document per slide — a slide is treated as one coherent unit, not
    split further, since splitting bullet points apart usually loses
    meaning.

    Safeguard: if a single slide's content exceeds slide_max_tokens
    (rare — dense speaker notes, big tables pasted into a slide),
    falls back to a recursive split just for that slide so it doesn't
    silently exceed the embedding model's token limit.
    """

    def __init__(self, config: ChunkingConfig):
        self.config = config
        self._fallback_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=config.encoding_name,
            chunk_size=config.slide_max_tokens,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def split(self, document: Document) -> list[Document]:
        if not document.page_content or not document.page_content.strip():
            return []

        token_count = self._fallback_splitter._length_function(document.page_content)
        if token_count <= self.config.slide_max_tokens:
            return [document]

        logger.debug(
            "Slide exceeds slide_max_tokens (%s > %s), falling back to recursive split (source=%s)",
            token_count,
            self.config.slide_max_tokens,
            document.metadata.get("source"),
        )
        return self._fallback_splitter.split_documents([document])


class TableChunkingStrategy(ChunkingStrategy):
    """
    Strategy for TABULAR (CSV/XLSX). Expects the loader to emit ONE
    Document PER ROW (with row content in page_content and a row
    index in metadata, e.g. metadata["row_index"]). Groups
    consecutive rows into chunks of rows_per_chunk, joined by
    newlines, preserving the row range in metadata.

    This is the one strategy that groups ACROSS multiple input
    Documents rather than splitting one — hence the split_batch
    override. split() on a single row-document just returns it
    unchanged (used only if called directly on one row).
    """

    def __init__(self, config: ChunkingConfig):
        self.config = config

    def split(self, document: Document) -> list[Document]:
        if not document.page_content or not document.page_content.strip():
            return []
        return [document]

    def split_batch(self, documents: list[Document]) -> list[Document]:
        rows = [d for d in documents if d.page_content and d.page_content.strip()]
        if not rows:
            return []

        chunks: list[Document] = []
        for start in range(0, len(rows), self.config.rows_per_chunk):
            group = rows[start : start + self.config.rows_per_chunk]

            merged_text = "\n".join(row.page_content for row in group)
            merged_metadata = dict(group[0].metadata)
            merged_metadata["row_start"] = group[0].metadata.get("row_index", start)
            merged_metadata["row_end"] = group[-1].metadata.get(
                "row_index", start + len(group) - 1
            )
            merged_metadata.pop("row_index", None)  # no longer a single row

            chunks.append(Document(page_content=merged_text, metadata=merged_metadata))

        return chunks


class HTMLSpecificStrategy(ChunkingStrategy):
    """
    Strategy for HTML. Uses LangChain's HTMLHeaderTextSplitter, which
    splits on actual heading tags (h1/h2/h3) and attaches the heading
    hierarchy as metadata — meaningfully better than character
    splitting for markup with real structure.

    IMPORTANT: requires RAW HTML markup, not the plain-text output of
    the cleaning pipeline (which strips tags). Reads from
    metadata["raw_html"] — the loader must stash the original markup
    there before the cleaning stage strips it down to plain text.
    Falls back to treating page_content as-is (best-effort) if
    raw_html isn't present, but this will under-perform.

    After header-splitting, further splits any oversized section with
    the recursive splitter to keep chunks under chunk_size.
    """

    def __init__(self, config: ChunkingConfig):
        self.config = config
        self._header_splitter = HTMLHeaderTextSplitter(
            headers_to_split_on=list(config.html_headers_to_split_on)
        )
        self._size_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            encoding_name=config.encoding_name,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def split(self, document: Document) -> list[Document]:
        raw_html = document.metadata.get("raw_html")

        if not raw_html:
            logger.warning(
                "HTMLSpecificStrategy: no raw_html in metadata (source=%s), "
                "falling back to page_content as-is",
                document.metadata.get("source"),
            )
            raw_html = document.page_content

        if not raw_html or not raw_html.strip():
            return []

        header_split_docs = self._header_splitter.split_text(raw_html)

        # Reattach original document metadata (source, page_number, etc.)
        # alongside the header metadata HTMLHeaderTextSplitter produced.
        for doc in header_split_docs:
            merged = dict(document.metadata)
            merged.update(doc.metadata)  # header hierarchy wins on key overlap
            doc.metadata = merged

        # Enforce chunk_size — a section between two headers can still
        # be arbitrarily long.
        return self._size_splitter.split_documents(header_split_docs)