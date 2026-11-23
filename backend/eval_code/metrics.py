# eval_code/metrics.py
"""
Metrics that need NO language model: they compare what the pipeline returned with the golden set using plain string
matching. Exact, free and reproducible, so they are the first thing to trust. (RAGAS, in ragas_scoring.py, adds
judgement-based metrics on top.) Same definitions as the documents evaluation, plus one for code: a citation must also
point at the right LINES of the right file.

Vocabulary:
  context / chunk   one retrieved passage handed to the LLM
  expected          the passage(s) that answer the question (from golden_set.jsonl)
  k                 how many chunks the pipeline hands to the LLM (5)
"""

import re
import statistics

K = 5


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def is_relevant(context: dict, requirement: dict) -> bool:
    """A chunk is relevant to a requirement if it comes from the right file AND contains the passage."""
    return context["source"] == requirement["doc"] and normalise(requirement["passage"]) in normalise(context["text"])


def retrieval_metrics(contexts: list[dict], expected: list[dict], k: int = K) -> dict | None:
    """
      recall@k     of the passages we NEEDED, which fraction showed up in the top k?
      hit@k        1 if ALL needed passages showed up, else 0
      precision@k  of the k chunks returned, which fraction were relevant?
      mrr          1 / (rank of the first relevant chunk): 1.0 if first, 0.5 if second, 0 if absent
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
      correct                  the answer is not a refusal and matches the golden answer pattern
      false_abstention         the model refused although the answer was in the code
      citation_hit             at least one cited file is an expected file
      citation_precision       of the cited files, which fraction are expected files
      citation_line_hit        a citation's line range overlaps the passage's real lines (right file, right lines)
      citation_line_precision  of the citations, which fraction are on target
    Out-of-scope questions:
      correct                  the model refused and cited nothing (it did not make something up)
    """
    cited = sample["cited_sources"]
    if not gold["answerable"]:
        return {"correct": 1.0 if sample["abstained"] and not cited else 0.0}

    expected_docs = {e["doc"] for e in gold["expected"]}
    matches_answer = re.search(gold["answer_regex"], sample["answer"], re.IGNORECASE) is not None
    result = {
        "correct": 1.0 if (not sample["abstained"] and matches_answer) else 0.0,
        "false_abstention": 1.0 if sample["abstained"] else 0.0,
        "citation_hit": 1.0 if expected_docs & set(cited) else 0.0,
        "citation_precision": (len(expected_docs & set(cited)) / len(set(cited))) if cited else None,
    }

    def on_target(citation: dict) -> bool:
        start, end = citation.get("start_line"), citation.get("end_line")
        file = citation.get("file_path") or citation.get("source")
        return start is not None and end is not None and any(
            file == e["doc"] and start <= e["lines"][1] and e["lines"][0] <= end for e in gold["expected"]
        )

    flags = [on_target(c) for c in sample.get("cited", [])]
    result["citation_line_hit"] = 1.0 if any(flags) else 0.0
    result["citation_line_precision"] = (sum(flags) / len(flags)) if flags else None
    return result


def mean(values) -> float | None:
    """Average ignoring missing values (None / NaN); None if there is nothing to average."""
    clean = [v for v in values if v is not None and v == v]
    return statistics.fmean(clean) if clean else None


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]
