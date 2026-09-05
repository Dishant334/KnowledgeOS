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
    """

    def expand(self, scored_chunks: list[ScoredChunk]) -> list[ScoredChunk]:
        for scored_chunk in scored_chunks:
            parent_content = scored_chunk.document.metadata.get("parent_content")

            if not parent_content:
                continue  # not a PROSE chunk, or no parent — leave as-is

            scored_chunk.document.page_content = parent_content
            scored_chunk.expanded = True

        return scored_chunks