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
        citations = build_citations(chunks)

        parts = []
        total_tokens = 0
        chunks_used = 0

        for scored_chunk, citation in zip(chunks, citations):
            text = scored_chunk.document.page_content
            token_count = len(self.encoding.encode(text))

            if total_tokens + token_count > self.max_context_tokens:
                continue

            parts.append(f"{citation.marker} {text}")
            total_tokens += token_count
            chunks_used += 1

        return AugmentedContext(
            prompt_context="\n\n".join(parts),
            citations=citations[:chunks_used],
            chunks_used=chunks_used,
            chunks_dropped=len(chunks) - chunks_used,
        )