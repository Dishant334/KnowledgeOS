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

Baseline = the Stage 2 splitter (85 chunks); `ast` = tree-sitter chunks (129); `ast_header` = AST plus the `# File: path | symbols` header. Judge: local Qwen3 8B. Full tables per configuration, speed, and the questions that changed: [`results/comparison.md`](results/comparison.md).

| Metric (hybrid + rerank) | Splitter (baseline) | AST chunks | AST + file header |
|---|---|---|---|
| Hit@5 | 0.86 | 0.79 | 0.79 |
| MRR | 0.77 | 0.80 | 0.83 |
| Answers correct | 0.79 | 0.86 | 1.00 |
| Cites the expected file AND its lines | 1.00 | 1.00 | 0.86 |
| RAGAS faithfulness | 0.89 | 0.94 | 0.93 |
| RAGAS context recall | 0.93 | 1.00 | 1.00 |
| Tokens per question | about 2,190 | about 1,590 | about 1,610 |

Under dense and hybrid search the AST chunker also improves retrieval (dense Hit@5 0.71 to 0.86, hybrid 0.86 to 0.93) and answers correct (up in all three configurations). Under hybrid + rerank, Hit@5 falls by one question (c13, a "global" question that is expected to fail) and citation line precision dips slightly. The `# File: path | symbols` header lifts answers correct further but lowers hybrid MRR (0.88 to 0.73) and line-accurate citations (1.00 to 0.86); its gain comes from three flipped questions and may be noise, so it stays **off** by default. **17 questions are few: one question is about 6 points**, so gaps of one or two questions are noise. The RAGAS judge is a small local model, so compare columns rather than trusting absolute values. The sealed test split (8 questions) has not been run yet. Full tables and the questions that flipped: [`backend/eval_code/results/comparison.md`](backend/eval_code/results/comparison.md).

**Decision:** `CODE_CHUNKER=ast` (default), `CODE_CHUNK_HEADER=false`. Revisit the header with a larger question set.
