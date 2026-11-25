# eval_code/pipelines.py
"""
Step 2 of a codebase evaluation run: for every golden question and every RETRIEVAL CONFIGURATION, run the real
pipeline and record what happened (contexts, answer, citations with their lines, timings).

The configurations differ only in how chunks are retrieved, so a difference in the final scores is caused by retrieval
(that is what makes it an "ablation"):

  dense                  dense vectors only (semantic similarity)
  hybrid                 dense + BM25 keywords, fused by Qdrant (reciprocal rank fusion)
  hybrid+rerank          hybrid, then a cross-encoder re-scores the top 15 candidates (no LLM in retrieval)

Everything after retrieval (prompt, LLM, citations, refusal logic) is identical for all three. The production /ask
endpoint also asks the LLM for paraphrases of the question; that is off by default there and not part of this evaluation.
"""

import time

from eval_code.ingest import EVAL_USER_ID

CONFIG_NAMES = ["dense", "hybrid", "hybrid+rerank"]
K = 5


def retrieve_chunks(config: str, question: str):
    """Returns the top-K chunks (as ScoredChunk objects, the type the generator expects)."""
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    from app.core.config import settings
    from app.retrieval.filters import build_qdrant_filter
    from app.retrieval.hybrid_search import hybrid_search
    from app.retrieval.model import RetrievalConfig, ScoredChunk
    from app.retrieval.orchestrator import get_search_store, retrieve

    k = settings.code_top_k                                   # chunks handed to the LLM (CODE_TOP_K, default 5)
    user_filter = build_qdrant_filter(uploaded_by=str(EVAL_USER_ID))
    hybrid_store = get_search_store()

    if config == "dense":
        dense_store = QdrantVectorStore(
            client=hybrid_store.client, collection_name=hybrid_store.collection_name, retrieval_mode=RetrievalMode.DENSE,
            embedding=hybrid_store.embeddings, vector_name=hybrid_store.vector_name,
        )
        hits = dense_store.similarity_search_with_score(question, k=k, filter=user_filter)
        return [ScoredChunk(document=doc, fused_score=score) for doc, score in hits]

    if config == "hybrid":
        return hybrid_search(hybrid_store, question, k=k, qdrant_filter=user_filter,
                             split_identifiers=settings.code_split_identifiers)   # the eval corpus is a code chat

    if config == "hybrid+rerank":
        return retrieve(question, user_id=EVAL_USER_ID, retrieval_config=RetrievalConfig(final_top_k=k, candidate_pool_size=max(30, k)), mode="code").chunks

    raise ValueError(f"unknown config {config!r}; use one of {CONFIG_NAMES}")


def describe(chunks) -> list[dict]:
    """ScoredChunk objects -> plain dicts (JSON-friendly, and what the metrics expect)."""
    return [
        {
            "text": chunk.document.page_content,
            "source": chunk.document.metadata.get("source_name"),
            "page": chunk.document.metadata.get("page_number"),
            "score": chunk.rerank_score if chunk.rerank_score is not None else chunk.fused_score,
            "file_path": chunk.document.metadata.get("file_path"),
            "start_line": chunk.document.metadata.get("start_line"),
            "end_line": chunk.document.metadata.get("end_line"),
        }
        for chunk in chunks
    ]


def contexts_in_prompt(chunks, mode: str = "code") -> list[dict]:
    """
    The chunks that really reached the LLM. The prompt builder keeps only what fits in its token budget (3000 tokens)
    and silently drops the rest. Evaluating "what was retrieved" instead of "what the LLM saw" would flatter the pipeline.
    """
    from app.augmentation.code_budget import get_code_context_builder
    from app.generation.orchestrator import get_context_builder

    builder = get_code_context_builder() if mode == "code" else get_context_builder()
    return describe(builder.build(chunks).used_chunks)


def run_question(config: str, gold: dict, llm, mode: str = "code") -> dict:
    """One golden question through one configuration. Returns a plain dict (a 'sample')."""
    from langchain_core.callbacks import get_usage_metadata_callback

    from app.generation.orchestrator import generate_answer

    started = time.perf_counter()
    chunks = retrieve_chunks(config, gold["question"])
    retrieval_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with get_usage_metadata_callback() as usage:        # collects the tokens the LLM reports
        result = generate_answer(gold["question"], llm, chunks, mode=mode)   # mode picks the prompt and the context budget
    generation_ms = (time.perf_counter() - started) * 1000

    tokens = sum(u.get("total_tokens", 0) for u in usage.usage_metadata.values())
    return {
        "id": gold["id"],
        "type": gold["type"],
        "config": config,
        "question": gold["question"],
        "reference": gold["reference"],
        "contexts": describe(chunks),                       # everything retrieval returned (top 5)
        "contexts_used": contexts_in_prompt(chunks, mode),        # the part of it that fit in the prompt
        "answer": result.answer,
        "abstained": result.abstained,
        "cited_sources": sorted({c.source_name for c in result.citations if c.source_name}),
        # what each citation pointed at (file and lines), to check it against the golden passage
        "cited": [{"source": c.source_name, "file_path": c.file_path, "start_line": c.start_line, "end_line": c.end_line} for c in result.citations],
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "tokens": tokens,
    }
