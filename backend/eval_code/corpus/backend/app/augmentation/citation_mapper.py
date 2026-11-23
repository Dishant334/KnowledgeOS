# app/augmentation/citation_mapper.py

from app.retrieval.model import ScoredChunk
from app.augmentation.model import Citation


# How much of the cited passage a citation carries (enough for a source card, small enough to store with every answer)
SNIPPET_CHARS = 600

# Metadata keys the HTML chunker writes for the headings above a chunk
HTML_HEADER_KEYS = ("Header 1", "Header 2", "Header 3")


def get_section_title(metadata: dict) -> str | None:
    """A readable section name, e.g. "Policy > Travel" (None if the chunk has no headings)."""
    if metadata.get("section_title"):
        return metadata["section_title"]

    headings = [metadata[key] for key in HTML_HEADER_KEYS if metadata.get(key)]
    return " > ".join(headings) or None


def make_snippet(text: str, max_chars: int = SNIPPET_CHARS) -> str:
    """The first max_chars characters of a passage (whitespace tidied), with "..." if it was cut."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def make_code_snippet(text: str, max_chars: int = SNIPPET_CHARS) -> str:
    """CODEBASE-FEATURE: like make_snippet but for code: newlines and indentation are KEPT (flattening them
    would destroy the code). Only leading blank lines and trailing whitespace are removed."""
    text = text.lstrip("\r\n").rstrip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def build_citations(chunks: list[ScoredChunk]) -> list[Citation]:
    """
    Assigns a [1], [2], [3]... marker to each chunk in order, and maps
    it back to enough source metadata for the frontend to render a
    clickable citation card. 
    """
    citations = []
    for i, scored_chunk in enumerate(chunks, start=1):
        metadata = scored_chunk.document.metadata
        citations.append(
            Citation(
                marker=f"[{i}]",
                document_id=metadata.get("document_id"),
                source_name=metadata.get("source_name", metadata.get("source")),
                page_number=metadata.get("page_number"),
                slide_number=metadata.get("slide_number"),
                section_title=get_section_title(metadata),
                sheet_name=metadata.get("sheet_name"),
                row_start=metadata.get("row_start"),
                row_end=metadata.get("row_end"),
                snippet=(
                    make_code_snippet(scored_chunk.document.page_content)   # CODEBASE-FEATURE
                    if metadata.get("language")
                    else make_snippet(scored_chunk.document.page_content)
                ),
                file_path=metadata.get("file_path"),                           # CODEBASE-FEATURE
                start_line=metadata.get("start_line"),
                end_line=metadata.get("end_line"),
                language=metadata.get("language"),
            )
        )
    return citations