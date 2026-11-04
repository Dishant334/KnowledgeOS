# eval/ragas_scoring.py
"""
Step 3 of an evaluation run: score every sample with RAGAS.

WHAT RAGAS DOES
Some qualities cannot be checked with string matching ("is every claim in this answer actually
supported by the retrieved text?"). RAGAS handles them with LLM-AS-A-JUDGE: it asks a language
model small, structured questions about each sample and turns the answers into numbers (0 to 1).

A RAGAS sample has four fields:
  user_input          the question
  retrieved_contexts  the passages the pipeline gave the LLM
  response            the answer the pipeline produced
  reference           the golden (ground truth) answer

THE FOUR METRICS (all 0..1, higher is better)

  faithfulness       "Did the answer stay inside the retrieved text?"  -> catches HALLUCINATION.
                     1. the judge splits the answer into single claims ("statements")
                     2. for each claim it checks whether the retrieved contexts support it
                     score = supported claims / all claims
                     Needs: question, contexts, response. (No reference.)

  answer_relevancy   "Does the answer address the question?"  -> catches off-topic / evasive answers.
                     1. the judge writes a few questions that the ANSWER would be a good reply to
                     2. we embed those and the real question and take their cosine similarity
                     score = average similarity
                     (a rambling or irrelevant answer yields questions unlike the original)
                     Needs: question, response, and an embedding model.

  context_precision  "Are the useful chunks ranked near the top?"  -> measures retrieval NOISE and ORDER.
                     1. the judge marks each retrieved chunk relevant / not relevant, using the reference
                     2. score = average of precision@rank over the relevant chunks, so relevant chunks
                        at rank 1 beat the same chunks at rank 5
                     Needs: question, contexts, reference.

  context_recall     "Did retrieval find everything needed to give the golden answer?"  -> measures MISSING info.
                     1. the judge splits the reference answer into sentences
                     2. for each, it checks whether it can be attributed to the retrieved contexts
                     score = attributable sentences / all sentences
                     Needs: contexts, reference.

HOW TO READ THEM TOGETHER
  low context_recall    -> retrieval missed information          (fix chunking / retrieval)
  low context_precision -> retrieval returned too much noise     (fix ranking / reranker / k)
  low faithfulness      -> the LLM invented things               (fix prompt / model)
  low answer_relevancy  -> the LLM answered a different question (fix prompt / model)

CAVEATS (be honest about these when you present numbers)
  * The judge is a model, so scores are noisy. A small local model (our default, free) is a weaker
    judge than a frontier model; use differences between configurations, not absolute values.
  * If the judge is the same model that wrote the answers (self-preference), scores run optimistic.
  * Judge outputs sometimes fail to parse; those samples get no score (counted and reported).
"""

import math

from eval.compat import install_ragas_compat

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
