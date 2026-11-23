# eval_code/run.py
"""
Run the codebase evaluation (separate from the documents evaluation in eval/; nothing here imports or changes it).

    cd backend
    python -m eval_code.run --tag baseline                      # dev split, 3 retrieval configurations, RAGAS (about an hour)
    python -m eval_code.run --tag ast --code-chunker ast        # the same questions with the AST chunker
    python -m eval_code.run --tag ast_header --code-header on   # ... with the "# File: path | symbol" header
    python -m eval_code.compare --run baseline=results/baseline --run ast=results/ast     # side by side, with RAGAS

The stages, in order (each one is a module in this folder):
  1. ingest.py         put the frozen source files into their own Qdrant collection (real ingestion code)
  2. pipelines.py      run every golden question through every retrieval configuration
  3. metrics.py        exact metrics (Hit@k, Recall, Precision, MRR, correctness, citations incl. LINES, refusals)
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
COLLECTION = "knowledgeos_eval_code"    # its own collection: never the real "documents", never the documents evaluation's


def parse_args(argv=None):
    from eval_code.pipelines import CONFIG_NAMES

    p = argparse.ArgumentParser(description="Evaluate the KnowledgeOS RAG pipeline on source code.")
    p.add_argument("--split", default="dev", choices=["dev", "test", "all"],
                   help="dev (17 questions, the default) is for tuning; test (8) is sealed and reported once at the end")
    p.add_argument("--tag", default=None, help="name of the results folder (default: the date and time)")
    p.add_argument("--code-chunker", default=None, choices=["ast", "splitter"],
                   help="how source files are chunked (default: the app's CODE_CHUNKER setting)")
    p.add_argument("--code-header", default=None, choices=["on", "off"],
                   help="put '# File: path | symbol' in front of each chunk (default: the app's CODE_CHUNK_HEADER setting)")
    p.add_argument("--configs", nargs="+", default=CONFIG_NAMES, choices=CONFIG_NAMES, help="retrieval configurations to compare")
    p.add_argument("--limit", type=int, default=None, help="only the first N golden questions (quick test)")
    p.add_argument("--types", nargs="+", default=None, help="only these question types (direct, paraphrase, ...)")
    p.add_argument("--generator", default="ollama", choices=["ollama", "gemini"], help="LLM that writes the answers")
    p.add_argument("--judge", default="ollama", choices=["ollama", "gemini"], help="LLM that judges for RAGAS")
    p.add_argument("--no-ragas", action="store_true", help="skip the (slow) RAGAS stage")
    p.add_argument("--skip-ingest", action="store_true", help="reuse the collection from an earlier run")
    p.add_argument("--workers", type=int, default=4, help="parallel judge calls for RAGAS")
    p.add_argument("--ragas-sample", type=int, default=None, help="score only N answerable questions with RAGAS (hard types first)")
    p.add_argument("--ragas-configs", nargs="+", default=None, choices=CONFIG_NAMES, help="score only these configurations with RAGAS")
    p.add_argument("--trace", action="store_true", help="send traces to LangSmith (off by default)")
    p.add_argument("--reuse", type=Path, default=None, help="results folder of an earlier run: finished stages are loaded, not redone")
    return p.parse_args(argv)


def configure_environment(args) -> None:
    """Must run BEFORE anything from `app` is imported: settings are read once, at import."""
    os.environ.setdefault("QDRANT_COLLECTION", COLLECTION)
    if args.code_chunker:                                             # an explicit experiment choice beats the app setting
        os.environ["CODE_CHUNKER"] = args.code_chunker
    if args.code_header:
        os.environ["CODE_CHUNK_HEADER"] = "true" if args.code_header == "on" else "false"
    os.environ["LANGSMITH_TRACING"] = "true" if args.trace else "false"
    os.environ.setdefault("UNSTRUCTURED_DISABLE_NOTICE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


def choose_golden(args) -> list[dict]:
    """The questions this run asks: the chosen split, then the --types and --limit filters."""
    from eval_code.suite import load_golden_set

    golden_list = load_golden_set(args.split)
    if args.types:
        golden_list = [g for g in golden_list if g["type"] in args.types]
    if args.limit:
        golden_list = golden_list[: args.limit]
    return golden_list


def choose_ragas_questions(golden_list: list[dict], n: int | None) -> set[str]:
    """RAGAS is slow, so it can run on a subset: every hard question first, then the easy 'direct' ones spread evenly."""
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


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


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
    from eval_code.ingest import ingest_corpus
    from eval_code.pipelines import run_question
    from eval_code.ragas_scoring import make_embeddings, make_judge, score_samples
    from eval_code.report import render_markdown, summarise_config, worst_questions

    out_dir = args.reuse or (RESULTS_DIR / (args.tag or datetime.now().strftime("%Y-%m-%d_%H%M")))
    out_dir.mkdir(parents=True, exist_ok=True)
    reuse = args.reuse is not None

    golden_list = choose_golden(args)
    golden = {g["id"]: g for g in golden_list}
    if args.split == "test":
        print("NOTE: the test split is sealed on purpose. Run it ONCE, for the final numbers, not while tuning.", flush=True)

    print(f"[1/4] ingesting the corpus into collection '{settings.qdrant_collection}' (chunker: {settings.code_chunker}, "
          f"header {'on' if settings.code_chunk_header else 'off'})", flush=True)
    corpus_info = {"documents": 0, "chunks": 0}
    if not args.skip_ingest:
        corpus_info = load_or_run(out_dir / "corpus.json", reuse, ingest_corpus)
    print(f"      {corpus_info['documents']} files -> {corpus_info['chunks']} chunks", flush=True)

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

        samples = load_or_run(out_dir / f"samples_{config}.json", reuse, run_all)
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
                    # object reused across loops fails with "Event loop is closed".
                    scored += score_samples(answerable[start : start + 8], make_judge(args.judge), embeddings, max_workers=args.workers)
                    done = len(scored)
                    eta = (time.time() - started) / done * (len(answerable) - done)
                    print(f"      {config}: {done}/{len(answerable)} scored (about {eta/60:.0f} min left)", end="\r", flush=True)
                print()
                return scored

            ragas_by_config[config] = {row["id"]: row for row in load_or_run(out_dir / f"ragas_{config}.json", reuse, score_all)}

    print("[4/4] writing the report", flush=True)
    summaries = {c: summarise_config(samples_by_config[c], golden, ragas_by_config.get(c)) for c in args.configs}
    chunking = f"{settings.code_chunker}, header {'on' if settings.code_chunk_header else 'off'}"
    info = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "questions": len(golden_list),
        "answerable": sum(g["answerable"] for g in golden_list), **corpus_info, "split": args.split, "chunking": chunking,
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
    (out_dir / "meta.json").write_text(json.dumps({**info, "tag": args.tag, "configs": args.configs}, indent=1))
    if out_dir.parent == RESULTS_DIR:      # only a normal run updates latest.md (not a run written elsewhere, e.g. by a test)
        (RESULTS_DIR / "latest.md").write_text(markdown)
    print(markdown)
    print(f"Raw samples and scores are in {out_dir}")
    return out_dir


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
