# Evaluating the RAG pipeline

A demo that "seems to work" is not evidence. This folder measures the pipeline with numbers, so a change
(a new reranker, a different chunk size, another LLM) can be judged by data instead of by feel.

```bash
cd backend
python -m eval.run                       # full run: 3 retrieval configurations, RAGAS with the local judge (about an hour)
python -m eval.run --limit 8 --no-ragas  # smoke test (a few minutes)
python -m eval.run --reuse eval/results/<folder>   # reload finished stages instead of redoing them
```

Needs: Qdrant running and Ollama running with `qwen3:8b` (`ollama pull qwen3:8b`). Install the extras with
`pip install -r requirements-eval.txt`. Everything runs locally, so a run costs nothing. It uses its own Qdrant
collection (`knowledgeos_eval`) and never touches your real documents.

## The idea in one picture

```
 golden_set.jsonl            corpus.py                      the REAL pipeline
 (question + right    +    (13 documents, 5     -->  ingest -> retrieve -> rerank -> LLM answer + citations
  answer + where it         file formats)                         |            |            |
  is found)                                                       v            v            v
                                                           retrieved      the answer   cited sources
                                                           chunks
                                      |                               |
                                      v                               v
                        EXACT metrics (metrics.py)         RAGAS metrics (ragas_scoring.py)
                        compare with the golden set        a judge LLM grades each sample
                        by string matching                          |
                                      \________________  ___________/
                                                       v
                                              report.md (a table per configuration)
```

## The six steps of an evaluation

| # | Step | Where | What happens |
|---|------|-------|--------------|
| 1 | Build a test set | `corpus.py`, `golden_set.jsonl` | We write documents whose content we control, and 45 questions with the exact sentence that answers each. Because we wrote the documents, the correct answer is known. |
| 2 | Ingest | `ingest.py` | The documents go through the production ingestion code into a separate Qdrant collection. |
| 3 | Run the pipeline | `pipelines.py` | Every question goes through three retrieval configurations; for each we save the retrieved chunks, the answer, the citations and the timings. The LLM, prompt and refusal logic are identical, so score differences come from retrieval. |
| 4 | Exact metrics | `metrics.py` | Hit/Recall/Precision@5, MRR, answer correctness, citation accuracy, refusal accuracy. No LLM involved: free, deterministic, trustworthy. |
| 5 | RAGAS metrics | `ragas_scoring.py` | An LLM judge grades faithfulness, answer relevancy, context precision and context recall. |
| 6 | Report | `report.py` | One table you can paste into a README, plus the questions that still fail. |

### The three retrieval configurations (an "ablation")

An ablation switches one component at a time to see what it is worth.

| name | what is different |
|---|---|
| `dense` | embedding similarity only |
| `hybrid` | dense + BM25 keyword search, merged by Qdrant (reciprocal rank fusion) |
| `hybrid+rerank` | hybrid candidates (15) re-scored by a cross-encoder, best 5 kept (no LLM in retrieval) |

### The golden set (`golden_set.jsonl`)

One JSON object per line: `question`, `reference` (the correct answer), `expected` (document + the sentence
that answers it), `answer_regex` (a loose pattern the final answer must match) and a `type`:

* `direct` the question reuses the document's words (the easy case)
* `paraphrase` almost no shared words, so keyword search alone fails and meaning-based search is needed
* `distractor` two documents (Europe vs US travel) differ only in numbers; retrieval must pick the right one
* `multi` the answer needs two facts, usually from two documents
* `out_of_scope` the documents do not contain the answer: the right behaviour is to refuse

## Metrics, with tiny examples

### Exact metrics (no LLM)

Say a question needs one sentence and the pipeline returns 5 chunks, 1 of which contains it:

* **Hit@5 / Recall@5** = was the needed passage among the 5? Here 1.0. (If a question needs 2 passages and 1 was found: recall 0.5, hit 0.)
* **Precision@5** = relevant chunks / 5. Here 1/5 = 0.20. It can never exceed 0.20 for a one-sentence answer, so compare configurations with it, do not read it as a grade.
* **MRR** = 1 / rank of the first relevant chunk. First place gives 1.0, second 0.5, fifth 0.2, absent 0. It rewards putting the right chunk at the top.
* **Answer correct** = the answer matches `answer_regex` and is not a refusal.
* **Citation hit / precision** = did the answer cite the right document, and how many of its citations were right.
* **Refuses out-of-scope** = for questions the documents cannot answer, did the model say so instead of inventing something.

### RAGAS metrics (LLM as judge)

Some qualities cannot be string-matched: "is every claim in this answer supported by the text?" RAGAS asks a judge
LLM small structured questions and converts the replies to a 0..1 score. Each sample has a question, the retrieved
contexts, the answer, and the reference answer.

| metric | the judge is asked | score | it catches |
|---|---|---|---|
| **faithfulness** | split the answer into single claims; is each claim supported by the contexts? | supported claims / all claims | hallucination |
| **answer relevancy** | which questions would this answer be a good reply to? (we embed them and compare with the real question) | average cosine similarity | evasive or off-topic answers |
| **context precision** | for each retrieved chunk, is it useful for the reference answer? | relevant chunks ranked higher score higher | noisy or badly ordered retrieval |
| **context recall** | split the reference answer into sentences; can each be found in the contexts? | found sentences / all sentences | information retrieval missed |

How to read them together:

| symptom | meaning | what to improve |
|---|---|---|
| low context recall | the needed text was not retrieved | chunking, hybrid search, k |
| low context precision | too much irrelevant text, or the good chunk is too low | reranker, k, chunk size |
| low faithfulness | the LLM added things that are not in the text | prompt, model |
| low answer relevancy | the LLM did not answer the question asked | prompt, model |

### Limits of an LLM judge (say these out loud when you present results)

* The judge is a model, so scores are **noisy**; some judge replies cannot be parsed and that sample gets no score (the report shows how many were scored).
* A small local judge (the free default) is weaker than a frontier model. Trust **differences between configurations** more than absolute values.
* If the judge is the same model that wrote the answers it tends to be generous (self-preference).
* That is why the exact metrics sit next to RAGAS: they cannot be fooled.

## Using it for real

* **Your own documents:** replace `build_corpus()` in `corpus.py` and rewrite `golden_set.jsonl`. 50 to 100 questions with known source sentences is a good size.
* **Another LLM:** `--generator gemini` or `--judge gemini` (watch the free-tier request limit).
* **See inside one question:** `--trace` sends traces to LangSmith; open a run to see the prompt, the retrieved chunks and their scores.
* **Regression check:** run before and after a change and compare `results/<run>/summary.json`.

## Experiment log

**Paraphrase questions and LLM query expansion (2026-11-05).** `/ask` asks the LLM for extra phrasings of the question before searching, but the three configurations above do not (retrieval is measured on its own). To see whether that closes the paraphrase gap (Hit@5 0.50) a fourth configuration was tried on all 45 questions and then removed:

| metric | hybrid+rerank | + LLM query expansion |
|---|---|---|
| Hit@5 | 0.93 | 0.93 |
| MRR | 0.85 | 0.84 |
| Answers correct | 0.93 | 0.93 |
| False refusals | 0.05 | 0.07 |
| Paraphrase Hit@5 (6 questions) | 0.50 | 0.50 |
| Retrieval latency p50 | 2.9 s | 9.9 s |

No gain, 3.4 times the retrieval time. Different questions fail in each: expansion finds passages the plain query misses (q35, q39) but for q34, q37 and q38 the needed chunk is in the 30-candidate pool (rank 6 to 10) and the cross-encoder drops it out of the top 5. So the bottleneck is reranking/fusion, not recall. The paraphrase prompt itself is not the slow part. Lesson: a small local model copies any example sentence in a prompt (it pasted one into 4 of 6 variants), so prompts here give vocabulary examples only. Ideas not yet tried: rerank against every variant, fuse variant rankings before reranking, smaller chunks, a stronger embedder.

## Compatibility note

RAGAS 0.4.3 imports two Google Vertex classes that `langchain-community` 0.4.2 no longer has, so `compat.py` installs
harmless stand-ins before `ragas` is imported. Delete it once RAGAS fixes the import.
