# Codebase evaluation: side-by-side comparison

Reference (first column): **baseline**. Every other cell shows its difference from the reference. All numbers were recomputed from each run's raw samples with the same code.

## Runs

| run | chunking | chunks | questions | RAGAS judge | commit |
|---|---|---|---|---|---|
| baseline | splitter, header off | 85 | 17 | ollama (qwen3:8b) | bdd9773 + uncommitted Stage 5/6 work |
| ast | ast, header off | 129 | 17 | ollama (qwen3:8b) | bdd9773 |
| ast_header | ast, header on | 129 | 17 | ollama (qwen3:8b) | bdd9773 |

## Retrieval configuration: `dense`

### Retrieval quality (exact)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Hit@5 (all needed passages found) | 0.71 | 0.86 (+0.14 better) | 0.79 (+0.07 better) |
| Recall@5 | 0.81 | 0.92 (+0.11 better) | 0.82 (+0.01 better) |
| Precision@5 (fraction of chunks that are relevant) | 0.20 | 0.23 (+0.03 better) | 0.19 (-0.01 worse) |
| MRR (right chunk near the top) | 0.60 | 0.77 (+0.17 better) | 0.65 (+0.05 better) |
| Needed passage actually reached the LLM (Hit in prompt) | 0.71 | 0.86 (+0.14 better) | 0.79 (+0.07 better) |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 (=) | 5.0 (=) |

### RAGAS (LLM judge, 0 to 1)

A small local judge is noisy: treat a gap of a few hundredths as no difference.

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Faithfulness (no hallucination) | 0.82 | 0.95 (+0.13 better) | 0.85 (+0.03 better) |
| Answer relevancy | 0.85 | 0.90 (+0.05 better) | 0.90 (+0.05 better) |
| Context precision | 0.72 | 0.78 (+0.06 better) | 0.85 (+0.12 better) |
| Context recall | 0.79 | 0.93 (+0.14 better) | 0.82 (+0.04 better) |

### Answer behaviour (exact)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Answers correct (matches golden answer) | 0.71 | 0.79 (+0.07 better) | 0.86 (+0.14 better) |
| False refusals (said no although answerable) | 0.07 | 0.00 (-0.07 better) | 0.00 (-0.07 better) |
| Cites an expected file | 0.93 | 1.00 (+0.07 better) | 1.00 (+0.07 better) |
| Citation precision | 1.00 | 1.00 (=) | 1.00 (=) |
| Cites the expected file AND its lines | 0.93 | 1.00 (+0.07 better) | 0.86 (-0.07 worse) |
| Citation line precision (citations on target) | 0.85 | 0.90 (+0.06 better) | 0.81 (-0.04 worse) |
| Refuses out-of-scope questions | 1.00 | 1.00 (=) | 1.00 (=) |

### Speed (rough)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Retrieval latency p50 (ms) | 372 | 342 (-30 better) | 285 (-87 better) |
| Generation latency p50 (s) | 6.9 | 8.6 (+1.7 worse) | 6.3 (-0.5 better) |
| Generation latency p95 (s) | 10.7 | 12.5 (+1.8 worse) | 12.6 (+1.9 worse) |
| Tokens per question | 2045 | 1505 (-539 better) | 1511 (-534 better) |

## Retrieval configuration: `hybrid`

### Retrieval quality (exact)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Hit@5 (all needed passages found) | 0.86 | 0.93 (+0.07 better) | 0.86 (=) |
| Recall@5 | 0.94 | 0.95 (+0.01 better) | 0.88 (-0.06 worse) |
| Precision@5 (fraction of chunks that are relevant) | 0.24 | 0.24 (=) | 0.21 (-0.03 worse) |
| MRR (right chunk near the top) | 0.88 | 0.82 (-0.06 worse) | 0.73 (-0.15 worse) |
| Needed passage actually reached the LLM (Hit in prompt) | 0.86 | 0.93 (+0.07 better) | 0.86 (=) |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 (=) | 5.0 (=) |

### RAGAS (LLM judge, 0 to 1)

A small local judge is noisy: treat a gap of a few hundredths as no difference.

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Faithfulness (no hallucination) | 0.95 | 0.95 (=) | 0.87 (-0.08 worse) |
| Answer relevancy | 0.92 | 0.90 (-0.02 worse) | 0.90 (-0.02 worse) |
| Context precision | 0.92 | 0.84 (-0.08 worse) | 0.91 (-0.01 worse) |
| Context recall | 1.00 | 1.00 (=) | 0.94 (-0.06 worse) |

### Answer behaviour (exact)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Answers correct (matches golden answer) | 0.79 | 0.86 (+0.07 better) | 0.93 (+0.14 better) |
| False refusals (said no although answerable) | 0.00 | 0.00 (=) | 0.00 (=) |
| Cites an expected file | 1.00 | 1.00 (=) | 1.00 (=) |
| Citation precision | 0.98 | 1.00 (+0.02 better) | 0.96 (-0.01 worse) |
| Cites the expected file AND its lines | 1.00 | 1.00 (=) | 0.86 (-0.14 worse) |
| Citation line precision (citations on target) | 0.98 | 0.94 (-0.04 worse) | 0.83 (-0.14 worse) |
| Refuses out-of-scope questions | 0.67 | 1.00 (+0.33 better) | 1.00 (+0.33 better) |

### Speed (rough)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Retrieval latency p50 (ms) | 347 | 296 (-51 better) | 313 (-34 better) |
| Generation latency p50 (s) | 8.7 | 5.8 (-2.9 better) | 5.8 (-2.8 better) |
| Generation latency p95 (s) | 16.8 | 10.8 (-6.1 better) | 12.8 (-4.1 better) |
| Tokens per question | 2142 | 1517 (-625 better) | 1585 (-557 better) |

## Retrieval configuration: `hybrid+rerank`

### Retrieval quality (exact)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Hit@5 (all needed passages found) | 0.86 | 0.79 (-0.07 worse) | 0.79 (-0.07 worse) |
| Recall@5 | 0.93 | 0.90 (-0.02 worse) | 0.90 (-0.02 worse) |
| Precision@5 (fraction of chunks that are relevant) | 0.24 | 0.23 (-0.01 worse) | 0.23 (-0.01 worse) |
| MRR (right chunk near the top) | 0.77 | 0.80 (+0.02 better) | 0.83 (+0.06 better) |
| Needed passage actually reached the LLM (Hit in prompt) | 0.86 | 0.79 (-0.07 worse) | 0.79 (-0.07 worse) |
| Chunks that fit in the prompt (of 5) | 5.0 | 5.0 (=) | 5.0 (=) |

### RAGAS (LLM judge, 0 to 1)

A small local judge is noisy: treat a gap of a few hundredths as no difference.

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Faithfulness (no hallucination) | 0.89 | 0.94 (+0.05 better) | 0.93 (+0.04 better) |
| Answer relevancy | 0.90 | 0.91 (+0.01 better) | 0.89 (-0.01 worse) |
| Context precision | 0.82 | 0.89 (+0.07 better) | 0.94 (+0.12 better) |
| Context recall | 0.93 | 1.00 (+0.07 better) | 1.00 (+0.07 better) |

### Answer behaviour (exact)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Answers correct (matches golden answer) | 0.79 | 0.86 (+0.07 better) | 1.00 (+0.21 better) |
| False refusals (said no although answerable) | 0.00 | 0.00 (=) | 0.00 (=) |
| Cites an expected file | 1.00 | 1.00 (=) | 1.00 (=) |
| Citation precision | 0.98 | 1.00 (+0.02 better) | 1.00 (+0.02 better) |
| Cites the expected file AND its lines | 1.00 | 1.00 (=) | 0.86 (-0.14 worse) |
| Citation line precision (citations on target) | 0.96 | 0.90 (-0.06 worse) | 0.82 (-0.14 worse) |
| Refuses out-of-scope questions | 1.00 | 1.00 (=) | 1.00 (=) |

### Speed (rough)

| metric | baseline | ast | ast_header |
|---|---|---|---|
| Retrieval latency p50 (ms) | 3218 | 2671 (-547 better) | 2802 (-416 better) |
| Generation latency p50 (s) | 9.8 | 6.2 (-3.6 better) | 6.3 (-3.6 better) |
| Generation latency p95 (s) | 15.9 | 12.7 (-3.2 better) | 10.4 (-5.5 better) |
| Tokens per question | 2191 | 1589 (-602 better) | 1609 (-582 better) |

## Which questions changed outcome

A question counts when its retrieval hit or its answer correctness differs from the reference run.

### ast vs baseline, `dense`: 2 question(s)

- c01 (direct): What does the take_token function do?  ->  retrieval hit 0 -> 1, answer correct 0 -> 1
- c11 (multi): What upload size limit does the backend enforce, and what does the frontend say when a file is bigger?  ->  retrieval hit 0 -> 1

### ast vs baseline, `hybrid`: 3 question(s)

- c08 (paraphrase): How are the separate pieces of a streamed answer told apart in the response body?  ->  answer correct 0 -> 1
- c11 (multi): What upload size limit does the backend enforce, and what does the frontend say when a file is bigger?  ->  retrieval hit 0 -> 1
- c16 (out_of_scope): Which payment provider handles the checkout?  ->  answer correct 0 -> 1

### ast vs baseline, `hybrid+rerank`: 2 question(s)

- c08 (paraphrase): How are the separate pieces of a streamed answer told apart in the response body?  ->  answer correct 0 -> 1
- c13 (global): In which files is the 20 MB file size limit written down?  ->  retrieval hit 1 -> 0

### ast_header vs baseline, `dense`: 2 question(s)

- c01 (direct): What does the take_token function do?  ->  retrieval hit 0 -> 1, answer correct 0 -> 1
- c08 (paraphrase): How are the separate pieces of a streamed answer told apart in the response body?  ->  answer correct 0 -> 1

### ast_header vs baseline, `hybrid`: 3 question(s)

- c08 (paraphrase): How are the separate pieces of a streamed answer told apart in the response body?  ->  answer correct 0 -> 1
- c13 (global): In which files is the 20 MB file size limit written down?  ->  answer correct 0 -> 1
- c16 (out_of_scope): Which payment provider handles the checkout?  ->  answer correct 0 -> 1

### ast_header vs baseline, `hybrid+rerank`: 3 question(s)

- c08 (paraphrase): How are the separate pieces of a streamed answer told apart in the response body?  ->  answer correct 0 -> 1
- c13 (global): In which files is the 20 MB file size limit written down?  ->  retrieval hit 1 -> 0, answer correct 0 -> 1
- c14 (global): Which parts of the project produce or handle a 429 Too Many Requests response?  ->  answer correct 0 -> 1

