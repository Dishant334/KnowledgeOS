# eval/run.py
"""
Run the whole evaluation:
The stages, in order (each one is a module in this folder):
  1. ingest.py         put the evaluation corpus into its own Qdrant collection (real ingestion code)
  2. pipelines.py      run every golden question through every retrieval configuration
  3. metrics.py        exact metrics (Hit@k, Recall, Precision, MRR, correctness, citations, refusals)
  4. ragas_scoring.py  RAGAS metrics (faithfulness, answer relevancy, context precision / recall)
  5. report.py         one markdown report + raw JSON for later analysis
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def parse_args(argv=None):
    from eval.pipelines import CONFIG_NAMES

    p = argparse.ArgumentParser(description="Evaluate the KnowledgeOS RAG pipeline.")
    p.add_argument("--configs", nargs="+", default=CONFIG_NAMES, choices=CONFIG_NAMES, help="retrieval configurations to compare")
    p.add_argument("--limit", type=int, default=None, help="only the first N golden questions (quick test)")
    p.add_argument("--types", nargs="+", default=None, help="only these question types (direct, paraphrase, ...)")
    p.add_argument("--generator", default="ollama", choices=["ollama", "gemini"], help="LLM that writes the answers")
    p.add_argument("--judge", default="ollama", choices=["ollama", "gemini"], help="LLM that judges for RAGAS")
    p.add_argument("--no-ragas", action="store_true", help="skip the (slow) RAGAS stage")
    p.add_argument("--skip-ingest", action="store_true", help="reuse the collection from an earlier run")
    p.add_argument("--workers", type=int, default=4, help="parallel judge calls for RAGAS")
    p.add_argument("--ragas-sample", type=int, default=None,
                   help="score only N answerable questions with RAGAS (same ones for every configuration; hard types first)")
    p.add_argument("--ragas-configs", nargs="+", default=None, choices=CONFIG_NAMES, help="score only these configurations with RAGAS (it is the slow stage)")
    p.add_argument("--trace", action="store_true", help="send traces to LangSmith (off by default: it is a lot of runs)")
    p.add_argument("--reuse", type=Path, default=None, help="results folder of an earlier run: finished stages are loaded, not redone")
    return p.parse_args(argv)


def configure_environment(args) -> None:
    """Must run BEFORE anything from `app` is imported: settings are read once, at import."""
    os.environ.setdefault("QDRANT_COLLECTION", "knowledgeos_eval")   # never the real "documents" collection
    os.environ["LANGSMITH_TRACING"] = "true" if args.trace else "false"
    os.environ.setdefault("UNSTRUCTURED_DISABLE_NOTICE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def choose_ragas_questions(golden_list: list[dict], n: int | None) -> set[str]:
    """
    RAGAS is slow (about 11 judge-LLM calls per sample), so it can run on a subset. The subset is
    STRATIFIED: every question of the hard types (paraphrase, distractor, multi) first, then the
    easy 'direct' questions spread evenly. It is the same subset for every configuration, so the
    configurations stay comparable.
    """
    answerable = [g for g in golden_list if g["answerable"]]
    if n is None or n >= len(answerable):
        return {g["id"] for g in answerable}

    chosen = [g for g in answerable if g["type"] != "direct"][:n]
    direct = [g for g in answerable if g["type"] == "direct"]
    room = n - len(chosen)
    if room > 0 and direct:
        step = max(1, len(direct) // room)
        chosen += direct[::step][:room]
    return {g["id"] for g in chosen}


def load_or_run(path: Path, reuse: bool, compute):
    """Stage cache: if the file exists (and we were asked to reuse), load it; otherwise compute and save it."""
    if reuse and path.exists():
        print(f"  (reusing {path.name})", flush=True)
        return json.loads(path.read_text())
    value = compute()
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False))
    return value


def main(argv=None) -> Path:
    args = parse_args(argv)
    configure_environment(args)

    from app.core.config import settings
    from app.generation.llm import build_llm
    from eval.ingest import ingest_corpus
    from eval.metrics import load_golden_set
    from eval.pipelines import fill_contexts_used, run_question
    from eval.ragas_scoring import make_embeddings, make_judge, score_samples
    from eval.report import render_markdown, summarise_config, worst_questions

    out_dir = args.reuse or (RESULTS_DIR / datetime.now().strftime("%Y-%m-%d_%H%M"))
    out_dir.mkdir(parents=True, exist_ok=True)
    reuse = args.reuse is not None

    golden_list = load_golden_set()
    if args.types:
        golden_list = [g for g in golden_list if g["type"] in args.types]
    if args.limit:
        golden_list = golden_list[: args.limit]
    golden = {g["id"]: g for g in golden_list}

    print(f"[1/4] ingesting the corpus into collection '{settings.qdrant_collection}'", flush=True)
    corpus_info = {"documents": 0, "chunks": 0}
    if not args.skip_ingest:
        corpus_info = load_or_run(out_dir / "corpus.json", reuse, ingest_corpus)
    print(f"      {corpus_info['documents']} documents -> {corpus_info['chunks']} chunks", flush=True)

    ragas_ids = choose_ragas_questions(golden_list, args.ragas_sample)
    llm = build_llm(args.generator)
    samples_by_config, ragas_by_config = {}, {}
    embeddings = None

    for config in args.configs:
        print(f"[2/4] answering {len(golden_list)} questions with retrieval config '{config}'", flush=True)

        def run_all():
            samples = []
            for i, gold in enumerate(golden_list, 1):
                samples.append(run_question(config, gold, llm))
                print(f"      {config}: {i}/{len(golden_list)}", end="\r", flush=True)
            print()
            return samples

        samples = [fill_contexts_used(s) for s in load_or_run(out_dir / f"samples_{config}.json", reuse, run_all)]
        samples_by_config[config] = [s for s in samples if s["id"] in golden]

        if not args.no_ragas and (args.ragas_configs is None or config in args.ragas_configs):
            answerable = [s for s in samples_by_config[config] if s["id"] in ragas_ids]
            print(f"[3/4] RAGAS ({args.judge} judge) on {len(answerable)} answerable samples for '{config}'", flush=True)

            def score_all():
                nonlocal embeddings
                embeddings = embeddings or make_embeddings()
                scored, started = [], time.time()
                for start in range(0, len(answerable), 8):      # small batches: progress output + less lost on a crash
                    # A NEW judge for every batch: each evaluate() call runs its own asyncio event loop, and an LLM
                    # object that is reused across loops fails with "Event loop is closed".
                    scored += score_samples(answerable[start : start + 8], make_judge(args.judge), embeddings, max_workers=args.workers)
                    done = len(scored)
                    eta = (time.time() - started) / done * (len(answerable) - done)
                    print(f"      {config}: {done}/{len(answerable)} scored (about {eta/60:.0f} min left)", end="\r", flush=True)
                print()
                return scored

            ragas_by_config[config] = {row["id"]: row for row in load_or_run(out_dir / f"ragas_{config}.json", reuse, score_all)}

    print("[4/4] writing the report", flush=True)
    summaries = {c: summarise_config(samples_by_config[c], golden, ragas_by_config.get(c)) for c in args.configs}
    info = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "questions": len(golden_list),
        "answerable": sum(g["answerable"] for g in golden_list), **corpus_info,
        "generator": f"{args.generator} ({settings.ollama_model if args.generator == 'ollama' else settings.gemini_model})",
        "judge": "none" if args.no_ragas else f"{args.judge} ({settings.ollama_model if args.judge == 'ollama' else settings.gemini_model})",
        "embedder": "BAAI/bge-large-en-v1.5 + BM25", "reranker": "BAAI/bge-reranker-base", "commit": git_commit(),
    }
    markdown = render_markdown(summaries, info)
    weak = worst_questions(samples_by_config, golden)
    if weak:
        markdown += f"\n## 6. Questions still failing in '{args.configs[-1]}' (where to look next)\n\n" + "\n".join(weak) + "\n"
    markdown += f"\n_commit {info['commit']}_\n"

    (out_dir / "report.md").write_text(markdown)
    (out_dir / "summary.json").write_text(json.dumps(summaries, indent=1, default=str))
    if out_dir.parent == RESULTS_DIR:      # only a normal run updates latest.md (not a run written elsewhere, e.g. by a test)
        (RESULTS_DIR / "latest.md").write_text(markdown)
    print(markdown)
    print(f"Raw samples and scores are in {out_dir}")
    return out_dir


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
