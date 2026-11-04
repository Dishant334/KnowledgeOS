# app/core/tracing.py
#
# Observability with LangSmith.
#
# LangChain chains (the query rewriter, the answer prompt | llm | parser, ...) are traced
# automatically once tracing is switched on (see export_tracing_environment in config.py).
# Our own retrieval steps are plain Python functions, so we mark them with @traceable
# to make them appear in the same trace tree:
#
#   ask                                  <- one user question, end to end
#   |-- retrieve
#   |   |-- (LLM) rewrite + paraphrase    <- LangChain, automatic
#   |   |-- hybrid_search (retriever)     <- chunks + scores found by dense + BM25
#   |   `-- rerank                        <- chunks + cross-encoder scores
#   |-- generate_answer
#   |   `-- (LLM) answer                  <- prompt, tokens, latency: automatic
#   `-- (LLM) summary / memory update
#
# When tracing is off, @traceable does almost nothing.
#
# What gets uploaded is chosen HERE, on purpose: each step logs a small summary of its
# inputs and outputs, never objects like the LLM, the database session or API keys.

from langsmith import traceable  # noqa: F401  (re-exported so other modules import it from one place)

PREVIEW_CHARS = 300


def pick(*names: str):
    """process_inputs helper: log only these arguments of the traced function."""
    return lambda inputs: {name: inputs[name] for name in names if name in inputs}


def describe_chunk(scored_chunk) -> dict:
    """A small, readable summary of one retrieved chunk (where it is from, its scores, a text preview)."""
    metadata = scored_chunk.document.metadata
    return {
        "source": metadata.get("source_name", metadata.get("source")),
        "page": metadata.get("page_number"),
        "slide": metadata.get("slide_number"),
        "fused_score": scored_chunk.fused_score,
        "rerank_score": scored_chunk.rerank_score,
        "text": " ".join(scored_chunk.document.page_content.split())[:PREVIEW_CHARS],
    }


def describe_chunks(scored_chunks) -> list[dict]:
    return [describe_chunk(chunk) for chunk in scored_chunks]
