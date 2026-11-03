# app/retrieval/parent_expander.py

import logging

from app.retrieval.model import ScoredChunk

logger = logging.getLogger(__name__)


class ParentExpander:
    """
    Swaps a chunk's page_content for its parent section's full text,
    read from metadata["parent_content"] — set during chunking by
    ParentChildStrategy (see app/ingestion/chunking/strategies.py).

    Runs AFTER reranking, not before: the cross-encoder should score
    against the precise child text (that's the whole point of
    searching on small chunks), and only the final winners get
    expanded to fuller context before being sent to the LLM.

    Not every chunk has parent_content — only PROSE (PDF/DOCX) chunks
    went through ParentChildStrategy. Slides/tabular/HTML chunks pass
    through unchanged.

    Several top chunks can share the same parent section. They would all
    expand to the same text, so only the best-ranked one is kept.
    """

    def expand(self, scored_chunks: list[ScoredChunk]) -> list[ScoredChunk]:
        result = []
        seen_parents = set()

        for scored_chunk in scored_chunks:
            metadata = scored_chunk.document.metadata
            parent_content = metadata.get("parent_content")

            if not parent_content:
                result.append(scored_chunk)  # not a PROSE chunk — leave as-is
                continue

            # Same section = same document AND same section text. (parent_id is NOT
            # enough: every page of a PDF numbers its sections from 0, so "file_p0"
            # repeats on each page and different pages would be wrongly merged.)
            parent_key = (metadata.get("document_id"), parent_content)
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)

            scored_chunk.document.page_content = parent_content
            scored_chunk.expanded = True
            result.append(scored_chunk)

        return result
