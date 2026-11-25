# Codebase evaluation: side-by-side comparison

Reference (first column): **ast**. Every other cell shows its difference from the reference. All numbers were recomputed from each run's raw samples with the same code.

## Runs

| run | chunking | chunks | questions | RAGAS judge | commit |
|---|---|---|---|---|---|
| ast | ast, header off | 129 | 17 | ollama (qwen3:8b) | bdd9773 |
| identifiers | ast, header off, identifiers split | 129 | 17 | ollama (qwen3:8b) | 29202e2 |

## Retrieval configuration: `dense`

### Retrieval quality (exact)

| metric | ast | identifiers |
|---|---|---|
| Hit@5 (all needed passages found) | 0.86 | 0.86 (=) |
| Recall@5 | 0.92 | 0.92 (=) |
| Precision@5 (fraction of chunks that are relevant) | 0.23 | 0.23 (=) |
| MRR (right chunk near the top) | 0.77 | 0.77 (=) |
| Needed passage actually reached the LLM (Hit in prompt) | 0.86 | 0.86 (=) |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 (=) |

### RAGAS (LLM judge, 0 to 1)

A small local judge is noisy: treat a gap of a few hundredths as no difference.

| metric | ast | identifiers |
|---|---|---|
| Faithfulness (no hallucination) | 0.95 | 0.96 (+0.01 better) |
| Answer relevancy | 0.90 | 0.90 (=) |
| Context precision | 0.78 | 0.78 (=) |
| Context recall | 0.93 | 0.93 (=) |

### Answer behaviour (exact)

| metric | ast | identifiers |
|---|---|---|
| Answers correct (matches golden answer) | 0.79 | 0.79 (=) |
| False refusals (said no although answerable) | 0.00 | 0.00 (=) |
| Cites an expected file | 1.00 | 1.00 (=) |
| Citation precision | 1.00 | 1.00 (=) |
| Cites the expected file AND its lines | 1.00 | 1.00 (=) |
| Citation line precision (citations on target) | 0.90 | 0.90 (=) |
| Refuses out-of-scope questions | 1.00 | 1.00 (=) |

### Speed (rough)

| metric | ast | identifiers |
|---|---|---|
| Retrieval latency p50 (ms) | 342 | 224 (-118 better) |
| Generation latency p50 (s) | 8.6 | 5.1 (-3.5 better) |
| Generation latency p95 (s) | 12.5 | 7.7 (-4.8 better) |
| Tokens per question | 1505 | 1505 (=) |

## Retrieval configuration: `hybrid`

### Retrieval quality (exact)

| metric | ast | identifiers |
|---|---|---|
| Hit@5 (all needed passages found) | 0.93 | 0.93 (=) |
| Recall@5 | 0.95 | 0.95 (=) |
| Precision@5 (fraction of chunks that are relevant) | 0.24 | 0.24 (=) |
| MRR (right chunk near the top) | 0.82 | 0.79 (-0.04 worse) |
| Needed passage actually reached the LLM (Hit in prompt) | 0.93 | 0.93 (=) |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 (=) |

### RAGAS (LLM judge, 0 to 1)

A small local judge is noisy: treat a gap of a few hundredths as no difference.

| metric | ast | identifiers |
|---|---|---|
| Faithfulness (no hallucination) | 0.95 | 0.96 (+0.01 better) |
| Answer relevancy | 0.90 | 0.91 (+0.01 better) |
| Context precision | 0.84 | 0.80 (-0.04 worse) |
| Context recall | 1.00 | 1.00 (=) |

### Answer behaviour (exact)

| metric | ast | identifiers |
|---|---|---|
| Answers correct (matches golden answer) | 0.86 | 0.86 (=) |
| False refusals (said no although answerable) | 0.00 | 0.00 (=) |
| Cites an expected file | 1.00 | 1.00 (=) |
| Citation precision | 1.00 | 1.00 (=) |
| Cites the expected file AND its lines | 1.00 | 1.00 (=) |
| Citation line precision (citations on target) | 0.94 | 0.94 (=) |
| Refuses out-of-scope questions | 1.00 | 0.67 (-0.33 worse) |

### Speed (rough)

| metric | ast | identifiers |
|---|---|---|
| Retrieval latency p50 (ms) | 296 | 257 (-39 better) |
| Generation latency p50 (s) | 5.8 | 5.8 (=) |
| Generation latency p95 (s) | 10.8 | 8.9 (-1.9 better) |
| Tokens per question | 1517 | 1538 (+21 worse) |

## Retrieval configuration: `hybrid+rerank`

### Retrieval quality (exact)

| metric | ast | identifiers |
|---|---|---|
| Hit@5 (all needed passages found) | 0.79 | 0.79 (=) |
| Recall@5 | 0.90 | 0.90 (=) |
| Precision@5 (fraction of chunks that are relevant) | 0.23 | 0.23 (=) |
| MRR (right chunk near the top) | 0.80 | 0.80 (=) |
| Needed passage actually reached the LLM (Hit in prompt) | 0.79 | 0.79 (=) |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 (=) |

### RAGAS (LLM judge, 0 to 1)

A small local judge is noisy: treat a gap of a few hundredths as no difference.

| metric | ast | identifiers |
|---|---|---|
| Faithfulness (no hallucination) | 0.94 | 0.94 (=) |
| Answer relevancy | 0.91 | 0.91 (=) |
| Context precision | 0.89 | 0.89 (=) |
| Context recall | 1.00 | 1.00 (=) |

### Answer behaviour (exact)

| metric | ast | identifiers |
|---|---|---|
| Answers correct (matches golden answer) | 0.86 | 0.86 (=) |
| False refusals (said no although answerable) | 0.00 | 0.00 (=) |
| Cites an expected file | 1.00 | 1.00 (=) |
| Citation precision | 1.00 | 1.00 (=) |
| Cites the expected file AND its lines | 1.00 | 1.00 (=) |
| Citation line precision (citations on target) | 0.90 | 0.90 (=) |
| Refuses out-of-scope questions | 1.00 | 1.00 (=) |

### Speed (rough)

| metric | ast | identifiers |
|---|---|---|
| Retrieval latency p50 (ms) | 2671 | 2627 (-44 better) |
| Generation latency p50 (s) | 6.2 | 6.0 (-0.3 better) |
| Generation latency p95 (s) | 12.7 | 10.9 (-1.8 better) |
| Tokens per question | 1589 | 1613 (+25 worse) |

## Which questions changed outcome

A question counts when its retrieval hit or its answer correctness differs from the reference run.

### identifiers vs ast, `dense`: 0 question(s)

- none

### identifiers vs ast, `hybrid`: 1 question(s)

- c16 (out_of_scope): Which payment provider handles the checkout?  ->  answer correct 1 -> 0

### identifiers vs ast, `hybrid+rerank`: 0 question(s)

- none

