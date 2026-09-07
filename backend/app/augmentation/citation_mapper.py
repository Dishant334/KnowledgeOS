# app/augmentation/citation_mapper.py

from app.retrieval.model import ScoredChunk
from app.augmentation.model import Citation


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
                document_id=metadata.get("document_id", "unknown"),
                source_name=metadata.get("source_name", metadata.get("source", "unknown")),
                page_number=metadata.get("page_number"),
                slide_number=metadata.get("slide_number"),
                section_title=metadata.get("section_title"),
            )
        )
    return citations