# eval/report.py
"""Step 4 of an evaluation run: turn raw samples + scores into a table you can paste in a README."""

from eval.metrics import answer_metrics, mean, percentile, retrieval_metrics
from eval.ragas_scoring import METRIC_NAMES


def summarise_config(samples: list[dict], golden: dict[str, dict], ragas_scores: dict[str, dict] | None) -> dict:
    """All numbers for ONE retrieval configuration."""
    retrieval, answers, answerable, out_of_scope, in_prompt = [], [], [], [], []
    for sample in samples:
        gold = golden[sample["id"]]
        r = retrieval_metrics(sample["contexts"], gold["expected"])
        a = answer_metrics(sample, gold)
        if r:
            retrieval.append(r)
            seen = retrieval_metrics(sample.get("contexts_used", sample["contexts"]), gold["expected"])
            in_prompt.append(seen["hit"])
        answers.append((gold, a))
        (answerable if gold["answerable"] else out_of_scope).append(a)

    summary = {
        "questions": len(samples),
        "hit@5": mean(r["hit"] for r in retrieval),
        "recall@5": mean(r["recall"] for r in retrieval),
        "precision@5": mean(r["precision"] for r in retrieval),
        "mrr": mean(r["mrr"] for r in retrieval),
        "hit_in_prompt": mean(in_prompt),
        "chunks_in_prompt": mean(len(s.get("contexts_used", s["contexts"])) for s in samples),
        "answer_correct": mean(a["correct"] for a in answerable),
        "false_abstention": mean(a["false_abstention"] for a in answerable),
        "citation_hit": mean(a["citation_hit"] for a in answerable),
        "citation_precision": mean(a["citation_precision"] for a in answerable),
        "refuses_out_of_scope": mean(a["correct"] for a in out_of_scope),
        "retrieval_ms_p50": percentile([s["retrieval_ms"] for s in samples], 0.5),
        "generation_s_p50": (percentile([s["generation_ms"] for s in samples], 0.5) or 0) / 1000,
        "generation_s_p95": (percentile([s["generation_ms"] for s in samples], 0.95) or 0) / 1000,
        "tokens_per_question": mean(s["tokens"] for s in samples),
    }

    by_type = {}
    for sample in samples:
        gold = golden[sample["id"]]
        r = retrieval_metrics(sample["contexts"], gold["expected"])
        if r:
            by_type.setdefault(gold["type"], []).append(r["hit"])
    summary["hit@5_by_type"] = {t: (mean(v), len(v)) for t, v in by_type.items()}

    if ragas_scores:
        for name in METRIC_NAMES:
            values = [ragas_scores[s["id"]][name] for s in samples if s["id"] in ragas_scores]
            summary[f"ragas_{name}"] = mean(values)
            summary[f"ragas_{name}_valid"] = f"{sum(v is not None for v in values)}/{len(values)}"
    return summary


def fmt(value, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def render_markdown(summaries: dict[str, dict], info: dict) -> str:
    configs = list(summaries)
    lines = [f"# RAG evaluation report\n", f"_{info['date']} | {info['questions']} questions ({info['answerable']} answerable, "
             f"{info['questions'] - info['answerable']} out of scope) | corpus: {info['documents']} documents, {info['chunks']} chunks_\n",
             f"Generator: **{info['generator']}** | RAGAS judge: **{info['judge']}** | embeddings: {info['embedder']} | reranker: {info['reranker']} | cost: 0\n"]

    def table(title, rows, note=""):
        lines.append(f"\n## {title}\n")
        if note:
            lines.append(f"{note}\n")
        lines.append("| metric | " + " | ".join(configs) + " |")
        lines.append("|---|" + "---|" * len(configs))
        for label, key, digits in rows:
            lines.append(f"| {label} | " + " | ".join(fmt(summaries[c].get(key), digits) for c in configs) + " |")

    table("1. Retrieval quality (no LLM, exact string matching)", [
        ("Hit@5 (all needed passages found)", "hit@5", 2), ("Recall@5", "recall@5", 2),
        ("Precision@5 (fraction of chunks that are relevant)", "precision@5", 2), ("MRR (right chunk near the top)", "mrr", 2),
        ("Needed passage actually reached the LLM (Hit in prompt)", "hit_in_prompt", 2), ("Chunks that fit in the prompt (of 5)", "chunks_in_prompt", 1),
    ], "Higher is better. Hit@5 and Recall@5 say whether the answer was found; Precision@5 and MRR say how clean and well ordered the results are. "
       "The last two rows show what survives the prompt's 3000-token budget: the prompt builder drops chunks that do not fit, so very large chunks could push relevant passages out before the LLM sees them.")

    if any("ragas_faithfulness" in s for s in summaries.values()):
        table("2. RAGAS (LLM-as-judge, 0 to 1)", [
            ("Faithfulness (no hallucination)", "ragas_faithfulness", 2), ("Answer relevancy", "ragas_answer_relevancy", 2),
            ("Context precision", "ragas_context_precision", 2), ("Context recall", "ragas_context_recall", 2),
        ], f"Judge: {info['judge']}. Use the DIFFERENCES between columns; a small local judge is noisy in absolute terms. "
           "Scored samples per metric: " + "; ".join(f"{c}: " + ", ".join(f"{n.replace('ragas_', '')} {summaries[c].get(n + '_valid', '-')}" for n in
                                                                          [f'ragas_{m}' for m in METRIC_NAMES]) for c in configs) + ".")

    table("3. Answer behaviour (exact checks)", [
        ("Answers correct (matches golden answer)", "answer_correct", 2), ("False refusals (said no although answerable)", "false_abstention", 2),
        ("Cites an expected document", "citation_hit", 2), ("Citation precision", "citation_precision", 2),
        ("Refuses out-of-scope questions", "refuses_out_of_scope", 2),
    ])
    table("4. Cost and speed", [
        ("Retrieval latency p50 (ms)", "retrieval_ms_p50", 0), ("Generation latency p50 (s)", "generation_s_p50", 1),
        ("Generation latency p95 (s)", "generation_s_p95", 1), ("Tokens per question", "tokens_per_question", 0),
    ], "Cost per query is 0 (local models only). Latencies were measured on a laptop that was also running the local judge and other work, so read them as rough; on an otherwise idle machine, retrieval with reranking takes about 0.2 s and a local answer about 1 to 4 s.")

    types = sorted({t for s in summaries.values() for t in s["hit@5_by_type"]})
    lines.append("\n## 5. Hit@5 by question type\n")
    lines.append("| type (n) | " + " | ".join(configs) + " |")
    lines.append("|---|" + "---|" * len(configs))
    for t in types:
        n = next(s["hit@5_by_type"][t][1] for s in summaries.values() if t in s["hit@5_by_type"])
        lines.append(f"| {t} ({n}) | " + " | ".join(fmt(summaries[c]["hit@5_by_type"].get(t, (None, 0))[0]) for c in configs) + " |")
    return "\n".join(lines) + "\n"


def worst_questions(samples_by_config: dict[str, list[dict]], golden: dict[str, dict], limit: int = 8) -> list[str]:
    """Questions where the best configuration still did not retrieve or answer correctly (where to look next)."""
    lines = []
    for sample in samples_by_config[list(samples_by_config)[-1]]:
        gold = golden[sample["id"]]
        r = retrieval_metrics(sample["contexts"], gold["expected"])
        a = answer_metrics(sample, gold)
        if (r and r["hit"] < 1) or a["correct"] < 1:
            lines.append(f"- {sample['id']} ({gold['type']}): {gold['question']}  ->  {sample['answer'][:110]!r}")
    return lines[:limit]
