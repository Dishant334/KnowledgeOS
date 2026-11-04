# eval/pipelines.py
"""
Step 2 of an evaluation run: for every golden question and every RETRIEVAL CONFIGURATION,
run the real pipeline and record what happened (contexts, answer, citations, timings).

The configurations differ only in how chunks are retrieved, so a difference in the final
scores is caused by retrieval (that is what makes it an "ablation"):

  dense                  dense vectors only (semantic similarity)
  hybrid                 dense + BM25 keywords, fused by Qdrant (reciprocal rank fusion)
  hybrid+rerank          hybrid, then a cross-encoder re-scores the top 15 candidates (no LLM in retrieval)

Everything after retrieval (prompt, LLM, citations, refusal logic) is identical for all three.
(The production /ask endpoint also asks the LLM for extra phrasings of the question before searching;
the evaluation leaves that out so retrieval is measured on its own.)
"""

import time

from eval.ingest import EVAL_USER_ID

CONFIG_NAMES = ["dense", "hybrid", "hybrid+rerank"]
K = 5


def retrieve_chunks(config: str, question: str):
    """Returns the top-K chunks (as ScoredChunk objects, the type the generator expects)."""
    from langchain_qdrant import QdrantVectorStore, RetrievalMode

    from app.retrieval.filters import build_qdrant_filter
    from app.retrieval.hybrid_search import hybrid_search
    from app.retrieval.model import RetrievalConfig, ScoredChunk
    from app.retrieval.orchestrator import get_search_store, retrieve

    user_filter = build_qdrant_filter(uploaded_by=str(EVAL_USER_ID))
    hybrid_store = get_search_store()

    if config == "dense":
        dense_store = QdrantVectorStore(
            client=hybrid_store.client, collection_name=hybrid_store.collection_name, retrieval_mode=RetrievalMode.DENSE,
            embedding=hybrid_store.embeddings, vector_name=hybrid_store.vector_name,
        )
        hits = dense_store.similarity_search_with_score(question, k=K, filter=user_filter)
        return [ScoredChunk(document=doc, fused_score=score) for doc, score in hits]

    if config == "hybrid":
        return hybrid_search(hybrid_store, question, k=K, qdrant_filter=user_filter)

    if config == "hybrid+rerank":
        return retrieve(question, user_id=EVAL_USER_ID, retrieval_config=RetrievalConfig(final_top_k=K)).chunks

    raise ValueError(f"unknown config {config!r}; use one of {CONFIG_NAMES}")


def describe(chunks) -> list[dict]:
    """ScoredChunk objects -> plain dicts (JSON-friendly, and what the metrics expect)."""
    return [
        {
            "text": chunk.document.page_content,
            "source": chunk.document.metadata.get("source_name"),
            "page": chunk.document.metadata.get("page_number"),
            "score": chunk.rerank_score if chunk.rerank_score is not None else chunk.fused_score,
        }
        for chunk in chunks
    ]


def contexts_in_prompt(chunks) -> list[dict]:
    """
    The chunks that really reached the LLM. The prompt builder keeps only what fits in its token
    budget (3000 tokens) and silently drops the rest, so with large chunks the LLM can see fewer
    passages than retrieval found. Evaluating "what was retrieved" instead of "what the LLM saw"
    would flatter the pipeline.
    """
    from app.generation.orchestrator import get_context_builder

    return describe(get_context_builder().build(chunks).used_chunks)


def fill_contexts_used(sample: dict) -> dict:
    """Samples saved by an older version of the harness lack `contexts_used`: work it out from the saved contexts."""
    if "contexts_used" not in sample:
        from langchain_core.documents import Document

        from app.retrieval.model import ScoredChunk

        chunks = [
            ScoredChunk(Document(page_content=c["text"], metadata={"source_name": c["source"], "page_number": c["page"]}), fused_score=c["score"])
            for c in sample["contexts"]
        ]
        sample["contexts_used"] = contexts_in_prompt(chunks)
    return sample


def run_question(config: str, gold: dict, llm) -> dict:
    """One golden question through one configuration. Returns a plain dict (a 'sample')."""
    from langchain_core.callbacks import get_usage_metadata_callback

    from app.generation.orchestrator import generate_answer

    started = time.perf_counter()
    chunks = retrieve_chunks(config, gold["question"])
    retrieval_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    with get_usage_metadata_callback() as usage:        # collects the tokens the LLM reports
        result = generate_answer(gold["question"], llm, chunks)
    generation_ms = (time.perf_counter() - started) * 1000

    tokens = sum(u.get("total_tokens", 0) for u in usage.usage_metadata.values())
    return {
        "id": gold["id"],
        "type": gold["type"],
        "config": config,
        "question": gold["question"],
        "reference": gold["reference"],
        "contexts": describe(chunks),                       # everything retrieval returned (top 5)
        "contexts_used": contexts_in_prompt(chunks),        # the part of it that fit in the prompt
        "answer": result.answer,
        "abstained": result.abstained,
        "cited_sources": sorted({c.source_name for c in result.citations if c.source_name}),
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "tokens": tokens,
    }
