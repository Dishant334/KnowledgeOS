# eval_code/ragas_scoring.py
"""
Step 3 of a codebase evaluation run: score every sample with RAGAS (LLM-as-judge). Same four metrics and the same
way of scoring as the documents evaluation (see eval/ragas_scoring.py for the long explanation); this copy exists so the
codebase evaluation does not depend on, or change, the documents one.

A RAGAS sample has four fields:  user_input (the question), retrieved_contexts (what the LLM saw), response (the answer),
reference (the golden answer).

  faithfulness       did the answer stay inside the retrieved code? (catches HALLUCINATION)
  answer_relevancy   does the answer address the question?          (catches off-topic / evasive answers)
  context_precision  are the useful chunks ranked near the top?     (measures retrieval NOISE and ORDER)
  context_recall     did retrieval find everything the golden answer needs? (measures MISSING information)

CAVEATS: the judge is a small local model (free), so scores are noisy; trust DIFFERENCES between runs more than absolute
values. It also reads code less well than prose, and it is the same model family that wrote the answers (self-preference).
Judge outputs sometimes fail to parse; those samples get no score (counted and reported).
"""

import math

from eval_code.compat import install_ragas_compat

METRIC_NAMES = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


def build_dataset(samples: list[dict]):
    """Our sample dicts -> a RAGAS EvaluationDataset."""
    install_ragas_compat()
    from ragas import EvaluationDataset

    return EvaluationDataset.from_list([
        {
            "user_input": s["question"],
            # what the LLM actually saw (the prompt builder drops chunks that exceed its token budget)
            "retrieved_contexts": [c["text"] for c in s.get("contexts_used", s["contexts"])],
            "response": s["answer"],
            "reference": s["reference"],
        }
        for s in samples
    ])


def make_judge(provider: str = "ollama"):
    """The LLM that judges. Defaults to the free local Qwen model."""
    install_ragas_compat()
    from ragas.llms import LangchainLLMWrapper

    from app.generation.llm import build_llm

    return LangchainLLMWrapper(build_llm(provider))


def make_embeddings():
    """The embedding model answer_relevancy needs: our own local bge-large (free)."""
    install_ragas_compat()
    from ragas.embeddings import LangchainEmbeddingsWrapper

    from app.ingestion.embedding.embedders import BGEM3DenseEmbedder
    from app.ingestion.embedding.models import EmbeddingConfig

    return LangchainEmbeddingsWrapper(BGEM3DenseEmbedder(EmbeddingConfig()))


def score_samples(samples: list[dict], judge, embeddings, max_workers: int = 4, timeout: int = 240) -> list[dict]:
    """
    Returns one dict per sample: {"id": ..., "faithfulness": 0.8, ...}. A metric the judge failed
    to produce (bad JSON, timeout) is None, so one flaky call never aborts a long evaluation.
    """
    install_ragas_compat()
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    from ragas.run_config import RunConfig

    if not samples:
        return []

    result = evaluate(
        build_dataset(samples),
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge,
        embeddings=embeddings,
        run_config=RunConfig(timeout=timeout, max_workers=max_workers),
        raise_exceptions=False,    # a failed judge call becomes NaN instead of crashing the run
        show_progress=False,
    )

    rows = result.to_pandas().to_dict("records")
    scores = []
    for sample, row in zip(samples, rows):
        entry = {"id": sample["id"]}
        for name in METRIC_NAMES:
            value = row.get(name)
            entry[name] = None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)
        scores.append(entry)
    return scores
