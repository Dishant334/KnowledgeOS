# Code RAG evaluation report

_2026-11-23 23:41 | 17 questions (14 answerable, 3 out of scope) | corpus: 24 source files, 85 chunks | split: dev | chunking: splitter, header off_

Generator: **ollama (qwen3:8b)** | RAGAS judge: **ollama (qwen3:8b)** | embeddings: BAAI/bge-large-en-v1.5 + BM25 | reranker: BAAI/bge-reranker-base | cost: 0


## 1. Retrieval quality (no LLM, exact string matching)

Higher is better. Hit@5 and Recall@5 say whether the answer was found; Precision@5 and MRR say how clean and well ordered the results are. The last two rows show what survives the prompt's 3000-token budget.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Hit@5 (all needed passages found) | 0.71 | 0.86 | 0.86 |
| Recall@5 | 0.81 | 0.94 | 0.93 |
| Precision@5 (fraction of chunks that are relevant) | 0.20 | 0.24 | 0.24 |
| MRR (right chunk near the top) | 0.60 | 0.88 | 0.77 |
| Needed passage actually reached the LLM (Hit in prompt) | 0.71 | 0.86 | 0.86 |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 | 5.0 |

## 2. RAGAS (LLM-as-judge, 0 to 1)

Judge: ollama (qwen3:8b). Use the DIFFERENCES between columns; a small local judge is noisy in absolute terms. Scored samples per metric: dense: faithfulness 14/14, answer_relevancy 14/14, context_precision 14/14, context_recall 14/14; hybrid: faithfulness 14/14, answer_relevancy 14/14, context_precision 14/14, context_recall 14/14; hybrid+rerank: faithfulness 14/14, answer_relevancy 14/14, context_precision 14/14, context_recall 14/14.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Faithfulness (no hallucination) | 0.82 | 0.95 | 0.89 |
| Answer relevancy | 0.85 | 0.92 | 0.90 |
| Context precision | 0.72 | 0.92 | 0.82 |
| Context recall | 0.79 | 1.00 | 0.93 |

## 3. Answer behaviour (exact checks)

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Answers correct (matches golden answer) | 0.71 | 0.79 | 0.79 |
| False refusals (said no although answerable) | 0.07 | 0.00 | 0.00 |
| Cites an expected file | 0.93 | 1.00 | 1.00 |
| Citation precision | 1.00 | 0.98 | 0.98 |
| Cites the expected file AND its lines | 0.93 | 1.00 | 1.00 |
| Citation line precision (citations on target) | 0.85 | 0.98 | 0.96 |
| Refuses out-of-scope questions | 1.00 | 0.67 | 1.00 |

## 4. Cost and speed

Cost per query is 0 (local models only). Latencies come from a laptop that was also doing other work: read them as rough.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Retrieval latency p50 (ms) | 372 | 347 | 3218 |
| Generation latency p50 (s) | 6.9 | 8.7 | 9.8 |
| Generation latency p95 (s) | 10.7 | 16.8 | 15.9 |
| Tokens per question | 2045 | 2142 | 2191 |

## 5. Hit@5 by question type

| type (n) | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| direct (5) | 0.80 | 1.00 | 1.00 |
| distractor (2) | 1.00 | 1.00 | 1.00 |
| global (2) | 0.00 | 0.50 | 1.00 |
| multi (2) | 0.50 | 0.50 | 0.00 |
| paraphrase (3) | 1.00 | 1.00 | 1.00 |

## 6. Questions still failing in 'hybrid+rerank' (where to look next)

- c08 (paraphrase): How are the separate pieces of a streamed answer told apart in the response body?  ->  'The separate pieces of a streamed answer are told apart by specific event markers in the response body. Each p'
- c11 (multi): What upload size limit does the backend enforce, and what does the frontend say when a file is bigger?  ->  'The backend enforces a maximum file size limit of 20 MB. When a file exceeds this limit, the frontend displays'
- c12 (multi): How does the backend recognise a secret-looking code file name, and what message does the user get?  ->  'The backend recognizes a secret-looking code file name by checking the file name against predefined policies. '
- c13 (global): In which files is the 20 MB file size limit written down?  ->  'The 20 MB file size limit is written down in the following files:\n\n1. In the context provided in [2], there is'
- c14 (global): Which parts of the project produce or handle a 429 Too Many Requests response?  ->  'The parts of the project that produce or handle a 429 Too Many Requests response are as follows:\n\n1. The `erro'

_commit bdd9773_
