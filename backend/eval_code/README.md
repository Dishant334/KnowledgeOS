# Evaluating the RAG pipeline on source code

The same idea as the documents evaluation in `../eval/`, for **code**: a demo that "seems to work" is not evidence, so
this folder measures the code-question pipeline with numbers. A change (a new chunker, a different reranker, another
LLM) is judged by data instead of by feel.

**This folder is separate on purpose.** It imports nothing from `eval/`, it has its own corpus, golden set, metrics,
RAGAS scoring, report and results, and its own Qdrant collection (`knowledgeos_eval_code`). The documents evaluation and
its tests are not touched by anything here (a test checks that nothing in this folder imports `eval`).

```bash
cd backend
python -m eval_code.run --tag baseline                     # dev split, 3 retrieval configurations, RAGAS (about an hour)
python -m eval_code.run --tag ast --code-chunker ast       # the same questions with the AST chunker (Stage 6)
python -m eval_code.run --tag ast_header --code-header on  # ... and with the "# File: path | symbol" header
python -m eval_code.compare --run baseline=eval_code/results/baseline --run ast=eval_code/results/ast \
                            --run ast_header=eval_code/results/ast_header --out eval_code/results/comparison.md
python -m eval_code.run --limit 3 --no-ragas               # smoke test (a few minutes)
```

Needs Qdrant running and Ollama running with `qwen3:8b`. Everything runs locally, so a run costs nothing.

## What is in the folder

| file | what it is |
|---|---|
| `corpus/` | a **frozen copy** of 24 files of this project (Python backend + JavaScript frontend, 2,902 lines). `MANIFEST.md` records the commit and a hash per file; a test fails if a file changes. |
| `golden_set.jsonl` | 25 questions, each with the verbatim passage that answers it, a `split` (`dev` 17 / `test` 8) and a type |
| `suite.py` | loads the corpus (through the project's own file policy) and the golden set; works out each passage's real line numbers |
| `ingest.py` | puts the corpus into its own Qdrant collection with the real ingestion code (refuses the production collection and the documents evaluation's) |
| `pipelines.py` | runs a question through one of the 3 retrieval configurations and records contexts, answer, citations **with their lines** |
| `metrics.py` | exact metrics, plus "cites the right file **and lines**" |
| `ragas_scoring.py`, `compat.py` | RAGAS (LLM-as-judge): faithfulness, answer relevancy, context precision, context recall |
| `report.py` | one report per run |
| `run.py` | the runner (`python -m eval_code.run`) |
| `compare.py` | side-by-side comparison of runs, with deltas and the questions that changed (`python -m eval_code.compare`) |
| `results/` | one folder per run (raw samples, RAGAS scores, `report.md`, `summary.json`, `meta.json`) and `comparison.md` |

## The questions

| type | n (dev / test) | what it checks |
|---|---|---|
| `direct` | 5 / 2 | the question names the function or identifier ("What does `take_token` do?") |
| `paraphrase` | 3 / 2 | the behaviour described without identifiers, so keyword search alone cannot find it |
| `distractor` | 2 / 1 | look-alike functions or files; retrieval must pick the right one |
| `multi` | 2 / 1 | the answer needs two facts from two places |
| `global` | 2 / 1 | "list everything / where is X handled": **expected to fail**, retrieval of 5 chunks cannot cover a whole repo |
| `out_of_scope` | 3 / 1 | the code does not contain the answer: the right behaviour is to refuse |

**Dev / test discipline.** Tune on `dev` (the default). The `test` split is sealed: `--split test` prints a reminder, and
it should be run **once**, at the end, for the final numbers. Run it while tuning and it stops being a test.

**Ground truth is verified, not trusted** (`tests/test_eval_code.py`): every expected passage appears **exactly once** in
its frozen file, every golden answer matches its own answer pattern, out-of-scope topics really are absent from the code,
and every passage lies **whole inside one chunk** after chunking (otherwise a question would measure where the chunker cut,
not retrieval).

## The metrics

* **Hit@5 / Recall@5 / Precision@5 / MRR**: from the retrieved chunks, by string matching. Hit needs *all* the passages a
  question needs (so `multi` and `global` questions are the hard ones).
* **Answers correct**, **false refusals**, **refuses out-of-scope**: from the final answer.
* **Cites an expected file** and **cites the expected file AND its lines** (new for code): a citation counts only if its
  `start_line..end_line` overlaps the passage's real lines in the right file. This also checks the line-number feature end to end.
* **RAGAS**: faithfulness (no invented claims), answer relevancy, context precision (noise and order), context recall (missing information).

### Limits to say out loud

* **17 dev questions are few.** One question is about 6 percentage points, so a gap of one or two questions is noise,
  not a trend. `compare` lists exactly which questions changed.
* The RAGAS judge is a small local model: it is noisy, reads code less well than prose, and is the same family that wrote
  the answers (self-preference). Trust differences between runs more than absolute values.
* The corpus is **our own code**, and the questions were written by someone who knows it.
* Latencies come from a laptop that was doing other things. Read them as rough.
* The baseline measures the pipeline **as it was before the AST chunker existed** (the Stage 2 splitter, docs prompt, 3,000-token
  context budget). The code prompt and a larger budget come in a later stage.

## Results (dev split, 17 questions)

Judge: local Qwen3 8B. Splitter = the Stage 2 splitter (85 chunks); AST = tree-sitter chunks (129); header = `# File: path | symbols` in front of each chunk; identifiers = `take_token` also indexed as `take token`. Per-run reports and the questions that changed: [`results/comparison.md`](results/comparison.md), [`results/comparison_identifiers.md`](results/comparison_identifiers.md).

| Metric (dev split, 17 questions) | Splitter (baseline) | AST | AST + header | AST + identifiers |
|---|---|---|---|---|
| Hit@5, dense | 0.71 | 0.86 | 0.79 | 0.86 |
| Hit@5, hybrid | 0.86 | 0.93 | 0.86 | 0.93 |
| Hit@5, hybrid+rerank | 0.86 | 0.79 | 0.79 | 0.79 |
| MRR, dense | 0.60 | 0.77 | 0.65 | 0.77 |
| MRR, hybrid | 0.88 | 0.82 | 0.73 | 0.79 |
| MRR, hybrid+rerank | 0.77 | 0.80 | 0.83 | 0.80 |
| Answers correct, dense | 0.71 | 0.79 | 0.86 | 0.79 |
| Answers correct, hybrid | 0.79 | 0.86 | 0.93 | 0.86 |
| Answers correct, hybrid+rerank | 0.79 | 0.86 | 1.00 | 0.86 |
| False refusals, hybrid+rerank | 0.00 | 0.00 | 0.00 | 0.00 |
| Refuses out-of-scope, hybrid | 0.67 | 1.00 | 1.00 | 0.67 |
| Refuses out-of-scope, hybrid+rerank | 1.00 | 1.00 | 1.00 | 1.00 |
| Cites right file AND lines, hybrid+rerank | 1.00 | 1.00 | 0.86 | 1.00 |
| Citation line precision, hybrid+rerank | 0.96 | 0.90 | 0.82 | 0.90 |
| RAGAS faithfulness, hybrid+rerank | 0.89 | 0.94 | 0.93 | 0.94 |
| RAGAS answer relevancy, hybrid+rerank | 0.90 | 0.91 | 0.89 | 0.91 |
| RAGAS context precision, hybrid+rerank | 0.82 | 0.89 | 0.94 | 0.89 |
| RAGAS context recall, hybrid+rerank | 0.93 | 1.00 | 1.00 | 1.00 |
| Tokens per question, hybrid+rerank | 2191 | 1589 | 1609 | 1613 |
| Generation p50 (s), hybrid+rerank | 9.8 | 6.2 | 6.3 | 6.0 |

Reading it: AST chunking is the one clear win (dense Hit@5 0.71 to 0.86, answers correct up in all three configurations, about 600 fewer tokens per question). Under hybrid + rerank Hit@5 is one question lower (c13, a global question expected to fail). The `# File: path | symbols` header lifts answers correct but costs line-accurate citations (1.00 to 0.86) and hybrid MRR, and its gain comes from three flipped questions, so it stays off. Splitting identifiers (`take_token` into `take token` for keyword search) changed nothing measurable (Hit@5 identical everywhere; the 0.67 in one cell is a single out-of-scope question), so it stays off by default. 17 questions are few: **one question is about 6 points**, so gaps of one or two questions are noise, and the RAGAS judge is a small local model, so compare columns rather than trusting absolute values. Stage 8 (the code prompt, the context budget and the no-cloud-fallback rule) is built but **not measured**: its eval was skipped on purpose. The sealed test split (8 questions) has not been run.

**Decision:** `CODE_CHUNKER=ast`, `CODE_CHUNK_HEADER=false`, `CODE_SPLIT_IDENTIFIERS=false`.
