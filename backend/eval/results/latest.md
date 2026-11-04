# RAG evaluation report

_2026-11-04 04:48 | 45 questions (42 answerable, 3 out of scope) | corpus: 13 documents, 121 chunks_

Generator: **ollama (qwen3:8b)** | RAGAS judge: **ollama (qwen3:8b)** | embeddings: BAAI/bge-large-en-v1.5 + BM25 | reranker: BAAI/bge-reranker-base | cost: 0


## 1. Retrieval quality (no LLM, exact string matching)

Higher is better. Hit@5 and Recall@5 say whether the answer was found; Precision@5 and MRR say how clean and well ordered the results are. The last two rows show what survives the prompt's 3000-token budget: the prompt builder drops chunks that do not fit, so very large chunks could push relevant passages out before the LLM sees them.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Hit@5 (all needed passages found) | 0.74 | 0.93 | 0.93 |
| Recall@5 | 0.75 | 0.93 | 0.93 |
| Precision@5 (fraction of chunks that are relevant) | 0.16 | 0.21 | 0.20 |
| MRR (right chunk near the top) | 0.55 | 0.78 | 0.85 |
| Needed passage actually reached the LLM (Hit in prompt) | 0.74 | 0.93 | 0.93 |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 | 5.0 |

## 2. RAGAS (LLM-as-judge, 0 to 1)

Judge: ollama (qwen3:8b). Use the DIFFERENCES between columns; a small local judge is noisy in absolute terms. Scored samples per metric: dense: faithfulness 20/20, answer_relevancy 20/20, context_precision 20/20, context_recall 20/20; hybrid: faithfulness 20/20, answer_relevancy 20/20, context_precision 20/20, context_recall 20/20; hybrid+rerank: faithfulness 20/20, answer_relevancy 20/20, context_precision 20/20, context_recall 20/20.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Faithfulness (no hallucination) | 0.80 | 0.75 | 0.82 |
| Answer relevancy | 0.63 | 0.74 | 0.73 |
| Context precision | 0.52 | 0.69 | 0.74 |
| Context recall | 0.70 | 0.85 | 0.85 |

## 3. Answer behaviour (exact checks)

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Answers correct (matches golden answer) | 0.74 | 0.93 | 0.93 |
| False refusals (said no although answerable) | 0.24 | 0.07 | 0.05 |
| Cites an expected document | 0.74 | 0.90 | 0.93 |
| Citation precision | 0.95 | 0.96 | 0.95 |
| Refuses out-of-scope questions | 1.00 | 1.00 | 1.00 |

## 4. Cost and speed

Cost per query is 0 (local models only). Latencies were measured on a laptop that was also running the local judge and other work, so read them as rough; on an otherwise idle machine, retrieval with reranking takes about 0.2 s and a local answer about 1 to 4 s.

| metric | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| Retrieval latency p50 (ms) | 203 | 310 | 2917 |
| Generation latency p50 (s) | 5.1 | 7.2 | 6.5 |
| Generation latency p95 (s) | 8.3 | 12.4 | 9.6 |
| Tokens per question | 1628 | 1689 | 1914 |

## 5. Hit@5 by question type

| type (n) | dense | hybrid | hybrid+rerank |
|---|---|---|---|
| direct (29) | 0.79 | 1.00 | 1.00 |
| distractor (4) | 1.00 | 1.00 | 1.00 |
| multi (3) | 0.33 | 1.00 | 1.00 |
| paraphrase (6) | 0.50 | 0.50 | 0.50 |

## 6. Questions still failing in 'hybrid+rerank' (where to look next)

- q35 (paraphrase): Can I add my husband or wife to my medical coverage?  ->  "I don't have enough information to answer that."
- q38 (paraphrase): Where can I borrow a temporary computer?  ->  'The context provided does not specify where you can borrow a temporary computer. However, it does mention that'
- q39 (paraphrase): When do new joiners get their work computer?  ->  'The context does not contain enough information to answer that.'

_commit dc76ef5_
