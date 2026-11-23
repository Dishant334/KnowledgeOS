# eval_code/compare.py
"""
Side-by-side comparison of runs of the codebase evaluation (for example: the Stage 2 splitter vs the AST chunker).

    cd backend
    python -m eval_code.compare --run baseline=eval_code/results/baseline --run ast=eval_code/results/ast \
                                --out eval_code/results/comparison.md

It does NOT trust the numbers a run printed. It reloads each run's raw samples (and RAGAS scores) and recomputes every
metric with the same code, so all columns are strictly like-for-like. The first run is the reference: every other column
shows its difference from it, and the report lists exactly which questions changed outcome (so a +0.06 is "one question",
not a trend).
"""

import argparse
import json
from pathlib import Path

from eval_code.metrics import answer_metrics, retrieval_metrics
from eval_code.pipelines import CONFIG_NAMES
from eval_code.report import ANSWER_ROWS, RAGAS_ROWS, RETRIEVAL_ROWS, SPEED_ROWS, fmt, summarise_config
from eval_code.suite import load_golden_set

# metrics where a LOWER number is the better one (a drop is an improvement)
LOWER_IS_BETTER = {"false_abstention", "retrieval_ms_p50", "generation_s_p50", "generation_s_p95", "tokens_per_question"}


def load_run(name: str, path: Path) -> dict:
    """One finished run folder -> its raw samples, RAGAS scores and metadata."""
    path = Path(path)
    run = {"name": name, "dir": str(path), "samples": {}, "ragas": {}, "meta": {}, "corpus": {}}
    if (path / "meta.json").exists():
        run["meta"] = json.loads((path / "meta.json").read_text())
    if (path / "corpus.json").exists():
        run["corpus"] = json.loads((path / "corpus.json").read_text())
    for config in CONFIG_NAMES:
        if (path / f"samples_{config}.json").exists():
            run["samples"][config] = json.loads((path / f"samples_{config}.json").read_text())
        if (path / f"ragas_{config}.json").exists():
            run["ragas"][config] = {row["id"]: row for row in json.loads((path / f"ragas_{config}.json").read_text())}
    if not run["samples"]:
        raise FileNotFoundError(f"{path} has no samples_*.json: is it a finished run folder?")
    return run


def summarise_run(run: dict, golden: dict[str, dict]) -> dict[str, dict]:
    """{config: summary}, computed fresh from the raw samples."""
    return {
        config: summarise_config([s for s in samples if s["id"] in golden], golden, run["ragas"].get(config))
        for config, samples in run["samples"].items()
    }


def question_changes(reference: dict, other: dict, golden: dict[str, dict], config: str) -> list[str]:
    """Questions whose retrieval hit or answer correctness differs between two runs (one configuration)."""
    ref = {s["id"]: s for s in reference["samples"].get(config, [])}
    lines = []
    for sample in other["samples"].get(config, []):
        before = ref.get(sample["id"])
        gold = golden.get(sample["id"])
        if before is None or gold is None:
            continue
        changes = []
        hit_before, hit_after = retrieval_metrics(before["contexts"], gold["expected"]), retrieval_metrics(sample["contexts"], gold["expected"])
        if hit_before and hit_after and hit_before["hit"] != hit_after["hit"]:
            changes.append(f"retrieval hit {hit_before['hit']:.0f} -> {hit_after['hit']:.0f}")
        ok_before, ok_after = answer_metrics(before, gold)["correct"], answer_metrics(sample, gold)["correct"]
        if ok_before != ok_after:
            changes.append(f"answer correct {ok_before:.0f} -> {ok_after:.0f}")
        if changes:
            lines.append(f"- {sample['id']} ({gold['type']}): {gold['question']}  ->  " + ", ".join(changes))
    return lines


def _cell(value, reference_value, key: str, digits: int, is_reference: bool) -> str:
    if value is None:
        return "-"
    text = fmt(value, digits)
    if is_reference or reference_value is None:
        return text
    delta = value - reference_value
    if abs(delta) < 0.5 * 10 ** -digits:
        return f"{text} (=)"
    sign = "+" if delta > 0 else "-"
    good = (delta < 0) == (key in LOWER_IS_BETTER)
    return f"{text} ({sign}{abs(delta):.{digits}f}{' better' if good else ' worse'})"


def render_comparison(runs: list[dict], summaries: dict[str, dict[str, dict]], golden: dict[str, dict]) -> str:
    names = [r["name"] for r in runs]
    lines = ["# Codebase evaluation: side-by-side comparison\n",
             f"Reference (first column): **{names[0]}**. Every other cell shows its difference from the reference. "
             "All numbers were recomputed from each run's raw samples with the same code.\n",
             "## Runs\n", "| run | chunking | chunks | questions | RAGAS judge | commit |", "|---|---|---|---|---|---|"]
    for run in runs:
        meta = run["meta"]
        questions = len({s['id'] for s in next(iter(run['samples'].values()))})
        lines.append(f"| {run['name']} | {meta.get('chunking', '?')} | {run['corpus'].get('chunks', meta.get('chunks', '?'))} | {questions} | "
                     f"{meta.get('judge', '?')} | {meta.get('commit', '?')} |")

    def table(title, rows, config, note=""):
        lines.append(f"\n### {title}\n")
        if note:
            lines.append(f"{note}\n")
        lines.append("| metric | " + " | ".join(names) + " |")
        lines.append("|---|" + "---|" * len(names))
        for label, key, digits in rows:
            reference_value = summaries[names[0]].get(config, {}).get(key)
            cells = [_cell(summaries[n].get(config, {}).get(key), reference_value, key, digits, i == 0) for i, n in enumerate(names)]
            lines.append(f"| {label} | " + " | ".join(cells) + " |")

    for config in CONFIG_NAMES:
        if not any(config in summaries[n] for n in names):
            continue
        lines.append(f"\n## Retrieval configuration: `{config}`")
        table("Retrieval quality (exact)", RETRIEVAL_ROWS, config)
        if any(f"ragas_faithfulness" in summaries[n].get(config, {}) for n in names):
            table("RAGAS (LLM judge, 0 to 1)", RAGAS_ROWS, config,
                  "A small local judge is noisy: treat a gap of a few hundredths as no difference.")
        table("Answer behaviour (exact)", ANSWER_ROWS, config)
        table("Speed (rough)", SPEED_ROWS, config)

    lines.append("\n## Which questions changed outcome\n")
    lines.append("A question counts when its retrieval hit or its answer correctness differs from the reference run.\n")
    for run in runs[1:]:
        for config in CONFIG_NAMES:
            if config not in run["samples"] or config not in runs[0]["samples"]:
                continue
            changes = question_changes(runs[0], run, golden, config)
            lines.append(f"### {run['name']} vs {names[0]}, `{config}`: {len(changes)} question(s)\n")
            lines.extend(changes or ["- none"])
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> Path:
    parser = argparse.ArgumentParser(description="Compare runs of the codebase evaluation side by side.")
    parser.add_argument("--run", action="append", required=True, metavar="NAME=FOLDER", help="a finished run; the first one is the reference")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "results" / "comparison.md")
    args = parser.parse_args(argv)

    runs = []
    for spec in args.run:
        if "=" not in spec:
            parser.error(f"--run expects NAME=FOLDER, got {spec!r}")
        name, folder = spec.split("=", 1)
        runs.append(load_run(name, Path(folder)))
    if len(runs) < 2:
        parser.error("give at least two --run options to compare")
    if len({r["name"] for r in runs}) != len(runs):
        parser.error("run names must be different")

    golden = {g["id"]: g for g in load_golden_set("all")}
    summaries = {r["name"]: summarise_run(r, golden) for r in runs}
    markdown = render_comparison(runs, summaries, golden)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown)
    print(markdown)
    print(f"Written to {args.out}")
    return args.out


if __name__ == "__main__":
    main()
