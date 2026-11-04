# eval/metrics.py
"""
Metrics that need NO language model: they compare what the pipeline returned with the
golden set using plain string matching. Exact, free and reproducible, so they are the
first thing to trust. (RAGAS, in ragas_scoring.py, adds judgement-based metrics on top.)

Vocabulary:
  context / chunk   one retrieved passage handed to the LLM
  expected          the sentence(s) that answer the question (from golden_set.jsonl)
  k                 how many chunks the pipeline hands to the LLM (5)
"""

import json
import re
import statistics
from pathlib import Path

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.jsonl"
K = 5


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def is_relevant(context: dict, requirement: dict) -> bool:
    """A chunk is relevant to a requirement if it comes from the right document AND contains the answer sentence."""
    return context["source"] == requirement["doc"] and normalise(requirement["passage"]) in normalise(context["text"])


def retrieval_metrics(contexts: list[dict], expected: list[dict], k: int = K) -> dict | None:
    """
    How good were the retrieved chunks?

      recall@k     of the passages we NEEDED, which fraction showed up in the top k?
                   (a question needing 2 facts and finding 1 has recall 0.5)
      hit@k        1 if ALL needed passages showed up, else 0
      precision@k  of the k chunks returned, which fraction were relevant? (less noise = higher)
      mrr          1 / (rank of the first relevant chunk): 1.0 if it is first, 0.5 if second, 0 if absent
                   (rewards putting the right chunk at the top)
    """
    if not expected:
        return None

    top = contexts[:k]
    found = [any(is_relevant(c, req) for c in top) for req in expected]
    relevant_flags = [any(is_relevant(c, req) for req in expected) for c in top]
    first_rank = next((i + 1 for i, flag in enumerate(relevant_flags) if flag), None)

    return {
        "recall": sum(found) / len(expected),
        "hit": 1.0 if all(found) else 0.0,
        "precision": sum(relevant_flags) / len(top) if top else 0.0,
        "mrr": 1 / first_rank if first_rank else 0.0,
    }


def answer_metrics(sample: dict, gold: dict) -> dict:
    """
    Did the final answer behave correctly?

    Answerable questions:
      correct             the answer is not a refusal and matches the golden answer pattern
      false_abstention    the model refused although the answer was in the documents
      citation_hit        at least one cited source is an expected document
      citation_precision  of the cited sources, which fraction are expected documents
    Out-of-scope questions:
      correct             the model refused and cited nothing (it did not make something up)
    """
    cited = sample["cited_sources"]
    if not gold["answerable"]:
        return {"correct": 1.0 if sample["abstained"] and not cited else 0.0}

    expected_docs = {e["doc"] for e in gold["expected"]}
    matches_answer = re.search(gold["answer_regex"], sample["answer"], re.IGNORECASE) is not None
    return {
        "correct": 1.0 if (not sample["abstained"] and matches_answer) else 0.0,
        "false_abstention": 1.0 if sample["abstained"] else 0.0,
        "citation_hit": 1.0 if expected_docs & set(cited) else 0.0,
        "citation_precision": (len(expected_docs & set(cited)) / len(set(cited))) if cited else None,
    }


def mean(values) -> float | None:
    """Average ignoring missing values (None / NaN); None if there is nothing to average."""
    clean = [v for v in values if v is not None and v == v]
    return statistics.fmean(clean) if clean else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]
