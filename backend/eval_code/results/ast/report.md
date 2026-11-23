# Code RAG evaluation report

_2026-11-24 00:28 | 17 questions (14 answerable, 3 out of scope) | corpus: 24 source files, 129 chunks | split: dev | chunking: ast, header off_

Generator: **ollama (qwen3:8b)** | RAGAS judge: **ollama (qwen3:8b)** | embeddings: BAAI/bge-large-en-v1.5 + BM25 | reranker: BAAI/bge-reranker-base | cost: 0


## 1. Retrieval quality (no LLM, exact string matching)

Higher is better. Hit@5 and Recall@5 say whether the answer was found; Precision@5 and MRR say how clean and well ordered the results are. The last two rows show what survives the prompt's 3000-token budget.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Hit@5 (all needed passages found) | 0.86 | 0.93 | 0.79 |
| Recall@5 | 0.92 | 0.95 | 0.90 |
| Precision@5 (fraction of chunks that are relevant) | 0.23 | 0.24 | 0.23 |
| MRR (right chunk near the top) | 0.77 | 0.82 | 0.80 |
| Needed passage actually reached the LLM (Hit in prompt) | 0.86 | 0.93 | 0.79 |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 | 5.0 |

## 2. RAGAS (LLM-as-judge, 0 to 1)

Judge: ollama (qwen3:8b). Use the DIFFERENCES between columns; a small local judge is noisy in absolute terms. Scored samples per metric: dense: faithfulness 14/14, answer_relevancy 14/14, context_precision 14/14, context_recall 14/14; hybrid: faithfulness 14/14, answer_relevancy 14/14, context_precision 14/14, context_recall 14/14; hybrid+rerank: faithfulness 14/14, answer_relevancy 14/14, context_precision 14/14, context_recall 14/14.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Faithfulness (no hallucination) | 0.95 | 0.95 | 0.94 |
| Answer relevancy | 0.90 | 0.90 | 0.91 |
| Context precision | 0.78 | 0.84 | 0.89 |
| Context recall | 0.93 | 1.00 | 1.00 |

## 3. Answer behaviour (exact checks)

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Answers correct (matches golden answer) | 0.79 | 0.86 | 0.86 |
| False refusals (said no although answerable) | 0.00 | 0.00 | 0.00 |
| Cites an expected file | 1.00 | 1.00 | 1.00 |
| Citation precision | 1.00 | 1.00 | 1.00 |
| Cites the expected file AND its lines | 1.00 | 1.00 | 1.00 |
| Citation line precision (citations on target) | 0.90 | 0.94 | 0.90 |
| Refuses out-of-scope questions | 1.00 | 1.00 | 1.00 |

## 4. Cost and speed

Cost per query is 0 (local models only). Latencies come from a laptop that was also doing other work: read them as rough.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Retrieval latency p50 (ms) | 342 | 296 | 2671 |
| Generation latency p50 (s) | 8.6 | 5.8 | 6.2 |
| Generation latency p95 (s) | 12.5 | 10.8 | 12.7 |
| Tokens per question | 1505 | 1517 | 1589 |

## 5. Hit@5 by question type

| type (n) | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| direct (5) | 1.00 | 1.00 | 1.00 |
| distractor (2) | 1.00 | 1.00 | 1.00 |
| global (2) | 0.00 | 0.50 | 0.50 |
| multi (2) | 1.00 | 1.00 | 0.00 |
| paraphrase (3) | 1.00 | 1.00 | 1.00 |

## 6. Questions still failing in 'hybrid+rerank' (where to look next)

- c11 (multi): What upload size limit does the backend enforce, and what does the frontend say when a file is bigger?  ->  'The backend enforces a maximum file size limit of 20 MB. If a file exceeds this size, the backend will refuse '
- c12 (multi): How does the backend recognise a secret-looking code file name, and what message does the user get?  ->  "The backend recognises a secret-looking code file name by checking the file's name against predefined policies"
- c13 (global): In which files is the 20 MB file size limit written down?  ->  'The 20 MB file size limit is mentioned in the following files:\n\n1. In the JavaScript file, the limit is define'
- c14 (global): Which parts of the project produce or handle a 429 Too Many Requests response?  ->  'The parts of the project that produce or handle a 429 Too Many Requests response include:\n\n1. The `reject` fun'

_commit bdd9773_
