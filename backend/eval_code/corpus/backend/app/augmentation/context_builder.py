# app/augmentation/context_builder.py

import tiktoken

from app.retrieval.model import ScoredChunk
from app.augmentation.model import AugmentedContext
from app.augmentation.citation_mapper import build_citations


class ContextBuilder:
    """
    Assembles reranked chunks into a token-budgeted context block,
    with numbered citation markers matching build_citations' output.
    Pure assembly — no LLM call happens here.
    """

    def __init__(self, max_context_tokens: int = 3000, encoding_name: str = "cl100k_base"):
        self.max_context_tokens = max_context_tokens
        self.encoding = tiktoken.get_encoding(encoding_name)

    def build(self, chunks: list[ScoredChunk]) -> AugmentedContext:
        # First pick the chunks that fit in the token budget...
        used_chunks = []
        total_tokens = 0

        for scored_chunk in chunks:
            token_count = len(self.encoding.encode(scored_chunk.document.page_content))

            if total_tokens + token_count > self.max_context_tokens:
                continue  # too big, try the next (smaller or lower-ranked) chunk

            used_chunks.append(scored_chunk)
            total_tokens += token_count

        # ...then number only those, so [1], [2], ... in the text always
        # match the citations list.
        citations = build_citations(used_chunks)
        parts = [
            f"{citation.marker} {scored_chunk.document.page_content}"
            for scored_chunk, citation in zip(used_chunks, citations)
        ]

        return AugmentedContext(
            prompt_context="\n\n".join(parts),
            citations=citations,
            chunks_used=len(used_chunks),
            chunks_dropped=len(chunks) - len(used_chunks),
            used_chunks=used_chunks,
        )
