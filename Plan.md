# Enterprise Knowledge Intelligence Platform — Resume-Grade Build Roadmap

A backend-first build order: get the RAG engine correct and *measured* before touching Docker, CI, or the UI. This sequencing means you understand every service before you containerize it, and you have working, evaluated intelligence before you spend a week on React. Single-tier auth (every employee has equal access — no RBAC/admin layer). LangChain is the implementation backbone throughout.

**Target: \~12 weeks part-time, \~7–8 weeks full-time.**

**Legend:** ✅ done and tested · 🟡 partly done · ⏳ not started. Status last reviewed 2026-11-05 against the code (441 tests passing).

---

## Phase 0 — Architecture & Planning (2–3 days)

> **Status: ✅ done** (decisions made and built). ⏳ Still open: a README with the architecture diagram (`Architecture.png` exists at the repo root) and a `/docs` schema doc. The evaluation code lives in `backend/eval/` rather than a top-level `/eval`.

**Goal:** Lock every major decision on paper so you're not re-architecting mid-build.

- Define the problem statement and user persona (employee asking questions against internal docs) in a 1-page doc. ✅
- Design the architecture diagram: React → FastAPI → Ingestion → Embeddings → Qdrant → Hybrid Retrieval → Reranker → Context Builder → LLM → Answer + Citations. Pin it in the README from day one.  ✅
- Decide the LLM (OpenAI or Gemini as primary; note where an open-source model via Ollama/vLLM could swap in — a pluggable LLM layer is its own talking point). ---> ✅ compareing gemini vs qwen
- Decide the embedding model (`text-embedding-3-large` vs. open-source `bge-large`/`e5-large` — note the cost/quality tradeoff you're making). 
  ✅ bge-large
- Decide the Qdrant collection schema up front: vector + payload (`doc_id, doc_type, uploaded_by, section, page, chunk_index, chunk_text`), and which payload fields need indexing for filtered search.
 ✅Point
├── id: chunk_id (UUID)
├── vectors
│   └── dense: embedding (float[])
│
└── payload
    ├── document_id       keyword    ✅ INDEX
    ├── chunk_id          keyword               # duplicate of point ID
    ├── uploaded_by       keyword    ✅ INDEX
    ├── doc_type          keyword    ✅ INDEX
    ├── mime_type         keyword
    ├── embedding_model   keyword    ✅ INDEX
    ├── source_name       keyword
    ├── source_uri        keyword
    ├── page_number       integer
    ├── section_title     keyword    🟡 optional
    ├── chunk_index       integer
    ├── total_chunks      integer
    ├── chunk_text        text
    ├── token_count       integer
    ├── language          keyword    🟡 optional
    ├── document_hash     keyword
    ├── content_hash      keyword
    └── created_at        datetime   ✅ INDEX

- Create the GitHub repo with `/backend`, `/eval`, `/docs` only. Deliberately **no frontend, no Docker, no CI/CD** yet — those come later once there's something real to containerize and test. ✅

**Deliverable:** README with architecture diagram, schema design doc, and repo skeleton pushed on day 1.

**Resume line:** *"Designed the end-to-end architecture and Qdrant schema for a production RAG platform before writing implementation code, including embedding model and LLM tradeoff analysis."*

---

## Phase 1 — FastAPI Backend Foundation (3–4 days)

> **Status: ✅ done.** Clerk JWT verification, `get_current_user`, `/auth/me`, user-isolated `/documents`, working `/retrieve` and `/ask`, Alembic migrations. Tested with mocked JWKS/svix and an isolated Postgres test DB. ⏳ A real Clerk browser login has not been verified by hand.

**Goal:** Backend-only skeleton with the real route surface, Clerk authentication, PostgreSQL persistence, and no RAG business logic yet.

```text
FastAPI
├── /health
├── /auth
│   └── /me
├── /documents
├── /retrieve
└── /ask
```

* FastAPI app with Pydantic models for every request/response — establish typed API contracts early.
* **Clerk authentication:** Clerk handles registration, login, sessions, and token issuance; FastAPI verifies Clerk JWTs and uses a dependency-injected `get_current_user` to identify the authenticated user.
* `/auth/me` — protected endpoint that resolves the authenticated Clerk user to the application's PostgreSQL user record.
* `/documents` (upload/list/delete stubs), `/retrieve` (stub), `/ask` (stub) — wired but not yet intelligent.
* File upload handling with multipart support, file-size limits, and file-type validation.
* Async endpoints where appropriate; centralized exception handlers from the start.
* PostgreSQL connection + Alembic migrations initialized for `users`, `documents`, `conversations`, and `messages`.
* `users` stores the application's user record and **Clerk user ID**, not passwords or authentication credentials.
* Protected document endpoints enforce user-level data isolation — users can only access their own documents.

> **Frontend readiness (✅ 2026-11-07):** CORS with env-driven origins (`CORS_ORIGINS`, exposes `Retry-After` and `X-RateLimit-*`), a friendly `failure_reason` on documents (raw error text stays private), and the unauthenticated `/test-db` debug route removed.

**Skills exercised:** FastAPI, Pydantic, Clerk authentication, JWT verification, dependency injection, PostgreSQL, Alembic, file uploads, async patterns, authorization, and error handling.

**Deliverable:** Swagger docs showing every route, Clerk-authenticated requests successfully verified by FastAPI, authenticated users mapped to PostgreSQL, protected document endpoints working with validation, and `/retrieve` and `/ask` wired as typed stubs.

**Resume line:** *"Built a typed, async FastAPI backend integrated with Clerk authentication, JWT verification, dependency-injected user context, PostgreSQL persistence, and centralized error handling as the foundation for a production RAG service."*

---


## Phase 2 — Document Ingestion ✅

**Goal:** Reliable ingestion for messy real-world files.

```
Upload → Postgres bytes → Celery worker → load / OCR → clean → chunk → bge-large + BM25 → Qdrant
```

**Built (✅):**
- Formats: PDF (OCR fallback with Tesseract), DOCX, TXT, Markdown, HTML, CSV, XLSX, PPTX.
- Cleaning: boilerplate, headers/footers, de-hyphenation, whitespace.
- Chunking: plain recursive 512-token splitter for prose; separate strategies for slides, tables (spreadsheet chunks never span two sheets) and HTML (`section_title`). **Parent/child chunking was tried and removed** — expanded chunks overflowed the 3000-token prompt budget.
- Per-user content-hash dedup (re-uploading the same file is a no-op), Celery background jobs with retries, advisory-lock duplicate control, per-document vector deletion.
- Status lifecycle: `pending → processing → ready | failed` (back to `pending` while retrying).

---

## Phase 3 — Embeddings + Qdrant (3–5 days)

> **Status: ✅ done.** Local `bge-large-en-v1.5` dense vectors + BM25 sparse vectors in Qdrant, payload indexes, batched embedding with retries, per-user filtered search. The ingestion folder script is `backend/eval/ingest.py` (reports documents and chunks indexed).

**Goal:** Understand and implement the vector layer solidly — this is foundational, not a library call to skim past.

```
Documents → Embeddings → Qdrant

```

- Implement embedding generation via LangChain's `OpenAIEmbeddings`/`HuggingFaceEmbeddings` wrapper — keeps the embedding provider swappable behind one interface.
- Batch embedding with retry/backoff for provider rate limits.
- Wire up Qdrant via LangChain's `QdrantVectorStore` integration (`add_documents`, `similarity_search`) rather than hand-rolling client calls.
- Build real understanding of: embeddings, vector similarity (cosine vs. dot product), collections, payload structure, metadata filtering, top-k retrieval mechanics — this is what you'll be asked to explain in an interview, so don't just call the library, know what it's doing underneath.
- Payload-indexed fields (`doc_type`, `doc_id`) for fast filtered search.

No frontend, no deployment concerns yet — purely get retrieval quality right in isolation.

**Deliverable:** Script that ingests a folder and reports "N chunks embedded, M vectors indexed," plus a manual sanity check: 5 known Q&A pairs, confirm top-k retrieval makes sense by eye.

**Resume line:** *"Implemented the embedding and vector storage layer with LangChain's Qdrant integration, including payload-indexed metadata fields enabling sub-100ms filtered similarity search."*

---

## Phase 4 — Advanced RAG ✅

**Goal:** Retrieval that finds the right chunk, not just similar text.

```
Query → rewrite + paraphrases → dense + BM25 (Qdrant RRF) → merge → cross-encoder rerank → top 5
```

**Built (✅):** implemented as our own code, not the LangChain `Ensemble` / `MultiQuery` / `ContextualCompression` classes.
- LLM query rewrite and paraphrases, hybrid dense + BM25 search with RRF fusion inside Qdrant, cached cross-encoder rerank (`bge-reranker-base`), always filtered to the current user. Models load lazily.
- `/retrieve` is live and traced in LangSmith.
- Measured: hybrid lifts Hit@5 from 0.74 to 0.93; the reranker lifts MRR from 0.78 to 0.85 (see Phase 6).



---

## Phase 5 — Generation ✅

**Goal:** Cited, grounded answers that say "I don't know" when the documents don't cover it.

```
Retrieved chunks → context builder → prompt → LLM → answer + citations
```

**Built (✅):**
- Context builder with a 3000-token budget; it reports which chunks really reached the prompt.
- Grounded prompt (document text is treated as untrusted), `[1]`-style citations mapped to document / page / section, refusal detection, and `/ask` returns only the sources the answer cites.
- Memory: old messages are never dropped; past 1500 tokens they fold into a rolling summary on `conversations.summary`. Long-term per-user facts live in Postgres via LangGraph `PostgresStore`, managed with `/memory` endpoints.
- LLM layer: local Qwen3 8B (Ollama) first, Gemini on error or quota. No provider working gives 503; quota gives 429.

**Streaming (✅):** `POST /ask/stream` sends the answer as Server-Sent Events (`token`, `done`, `error`) while the model writes it; `POST /ask` still returns the whole answer as JSON. Both run the same code (`stream_answer` / `ask_stream`).

**Citations for the frontend (✅):** each answer's citations (source, page/section/sheet/slide, plus a `snippet` of the cited passage) are saved with the message. `GET /conversations/{id}` returns the whole chat with all citations in a single request, and `GET /conversations` lists conversations for a sidebar.

**Conversation management (✅):** `POST /conversations` starts an empty "New chat" (named from its first question), `PATCH /conversations/{id}` renames, `DELETE /conversations/{id}` removes the chat with its messages and citations (documents and long-term memory facts stay).

**Deferred until the frontend exists:** an endpoint that shows conversation summaries.

---

## Phase 6 — Evaluation 🟡

**Goal:** Prove the system works with numbers.

**Built (✅):** harness in `backend/eval/` — 45-question golden set over 13 synthetic documents (5 formats), exact metrics (Hit/Recall/Precision@5, MRR, answer correctness, citations, refusals), RAGAS 0.4.3 (faithfulness, answer relevancy, context precision, context recall) with a local Qwen judge, a three-configuration comparison, p50/p95 latency and token counts, and LangSmith tracing (verified live).

### Results

| | |
|---|---|
| **Measured** | 2026-11-04 |
| **Test set** | 45 questions (42 answerable, 3 out of scope), 13 synthetic documents in 5 formats, 121 chunks |
| **Models** | Qwen3 8B (local) writes the answers *and* judges; `bge-large` embeddings + BM25; `bge-reranker-base` |
| **RAGAS** | run on a fixed stratified subset of 20 questions (same ones for every setup) |
| **Cost** | 0 per query (all local) |
| **Full report** | `backend/eval/results/latest.md` |

Three retrieval setups are compared; only retrieval differs, the prompt, LLM and citation logic are identical. **Bold = best in the row.**

**1. Retrieval quality** (exact string matching, no LLM)

| Metric | Dense only | + BM25 hybrid | + Reranker |
|---|:---:|:---:|:---:|
| Hit@5: needed passage found | 0.74 | **0.93** | **0.93** |
| Recall@5 | 0.75 | **0.93** | **0.93** |
| Precision@5 (ceiling 0.20) | 0.16 | **0.21** | 0.20 |
| MRR: right chunk near the top | 0.55 | 0.78 | **0.85** |

**2. Answer quality** (exact checks against the golden answers)

| Metric | Dense only | + BM25 hybrid | + Reranker |
|---|:---:|:---:|:---:|
| Answers correct | 0.74 | **0.93** | **0.93** |
| False refusals (lower is better) | 0.24 | 0.07 | **0.05** |
| Cites an expected document | 0.74 | 0.90 | **0.93** |
| Citation precision | 0.95 | **0.96** | 0.95 |
| Out-of-scope questions refused | **1.00** | **1.00** | **1.00** |

**3. RAGAS** (LLM-as-judge, 0 to 1; use the differences between columns, not the absolute values)

| Metric | Dense only | + BM25 hybrid | + Reranker |
|---|:---:|:---:|:---:|
| Faithfulness (no hallucination) | 0.80 | 0.75 | **0.82** |
| Answer relevancy | 0.63 | **0.74** | 0.73 |
| Context precision | 0.52 | 0.69 | **0.74** |
| Context recall | 0.70 | **0.85** | **0.85** |

**4. Speed and tokens** (measured on a busy laptop, so rough; idle, retrieval with rerank takes about 0.2 s and a local answer 1 to 4 s)

| Metric | Dense only | + BM25 hybrid | + Reranker |
|---|:---:|:---:|:---:|
| Retrieval latency p50 | 203 ms | 310 ms | 2917 ms |
| Generation latency p50 / p95 | 5.1 / 8.3 s | 7.2 / 12.4 s | 6.5 / 9.6 s |
| Tokens per question | 1628 | 1689 | 1914 |

**5. Hit@5 by question type**

| Question type (count) | Dense only | + BM25 hybrid | + Reranker |
|---|:---:|:---:|:---:|
| Direct (29) | 0.79 | **1.00** | **1.00** |
| Multi-document (3) | 0.33 | **1.00** | **1.00** |
| Distractor (4) | **1.00** | **1.00** | **1.00** |
| Paraphrase (6) | 0.50 | 0.50 | 0.50 |

#### What it shows
- **Hybrid search is the big win:** Hit@5 rises from 0.74 to 0.93, mostly on multi-document questions (0.33 to 1.00), and false refusals fall from 24% to 7%.
- **The reranker improves ordering, not coverage:** MRR 0.78 to 0.85 and context precision 0.69 to 0.74, but Hit@5 stays 0.93. It costs retrieval time (310 ms to 2917 ms in this busy-machine run).
- **Paraphrase questions are unsolved:** 0.50 in every setup. A trial of LLM query expansion did not help (see `backend/eval/README.md`, Experiment log).
- **Faithfulness (0.75 to 0.82) is within judge noise;** do not read a winner into it.

#### Caveats
- The judge is the same model that wrote the answers, so it tends to score generously. That is why exact metrics sit next to RAGAS: they cannot be fooled.
- The corpus is small and synthetic, and RAGAS covers 20 of the 42 answerable questions.

**Still pending (⏳):** grow the golden set from 45 to 50–100 questions, ideally with real documents.

**Resume line:** *"Built a RAGAS and exact-metric evaluation harness traced via LangSmith; it showed hybrid search raising Hit@5 from 0.74 to 0.93 and reranking raising MRR from 0.78 to 0.85 on a 45-question golden set, and surfaced a paraphrase-query weakness to fix next."*

---

## Phase 6 addendum — The evaluation harness

Code: `backend/eval/` (full guide: `backend/eval/README.md`). It runs the **real** ingestion, retrieval and generation code, so the numbers describe the actual product, not a mock.

### How a run flows
```text
 corpus.py ──► ingest.py ──► Qdrant (own collection: knowledgeos_eval)
                                         │
 golden_set.jsonl ──► pipelines.py: each question x 3 retrieval setups
 (question + answer      │          then the real generator
  + where it is)         ▼
              ┌──────────┴───────────┐
              ▼                      ▼
     metrics.py (exact)      ragas_scoring.py (LLM judge)
              └──────────┬───────────┘
                         ▼
          report.py ──► report.md + summary.json
```

### Run it
Everything runs from `backend/`.

```bash
# one-time setup
docker compose up -d qdrant                    # the eval needs Qdrant only (not Postgres or Redis)
ollama pull qwen3:8b                           # generator and judge (local, free)
pip install -r requirements-eval.txt           # requirements.txt + ragas==0.4.3
OLLAMA_NUM_PARALLEL=4 ollama serve             # RAGAS makes about 11 judge calls per answer

# runs
python -m eval.run                             # full run, about an hour
python -m eval.run --limit 8 --no-ragas        # smoke test, a few minutes
python -m eval.run --ragas-sample 20           # RAGAS on 20 questions only
python -m eval.run --reuse eval/results/<run>  # reload finished stages instead of redoing them

# tests for the harness itself
pytest -q tests/test_eval_harness.py           # 29 tests
```

Other flags: `--configs`, `--types`, `--limit`, `--skip-ingest`, `--generator` / `--judge` (`ollama` or `gemini`), `--trace` (LangSmith, off by default).

### What each file does
| Step | File | Role |
|:---:|---|---|
| – | `run.py` | Conductor: parses flags, forces the separate `knowledgeos_eval` collection and tracing off, runs the stages, caches each one to JSON (`--reuse`). |
| 1 | `corpus.py` | Builds 13 synthetic documents in 5 formats with deliberate traps (Europe vs US travel policy, answers split across documents). Deterministic. |
| 1 | `golden_set.jsonl` | The answer key: 45 questions, each with the correct answer, the exact sentence that answers it, and a type. |
| 2 | `ingest.py` | Loads the corpus with the production `ingest_file()` under a fake user. Refuses to run against the real `documents` collection. |
| 3 | `pipelines.py` | Runs every question through `dense`, `hybrid` and `hybrid+rerank`, then the real `generate_answer()`; records timings, tokens and which chunks fit the prompt. |
| 4 | `metrics.py` | Exact, no-LLM metrics by string matching. |
| 5 | `ragas_scoring.py` | RAGAS metrics with the local judge. A failed judge call becomes NaN, not a crash. |
| 6 | `report.py` | Builds the tables, Hit@5 by question type, and the list of questions that still fail. |
| – | `compat.py` | Stand-ins for two Vertex classes RAGAS 0.4.3 imports but `langchain-community` no longer has. Delete when RAGAS fixes it. |

### The metrics in one table
| Metric | Kind | Question it answers | Catches |
|---|---|---|---|
| Hit@5 / Recall@5 | exact | Was the needed passage in the top 5? | retrieval misses |
| Precision@5 | exact | What fraction of the 5 chunks is relevant? | noisy retrieval |
| MRR | exact | How high is the first right chunk? (1.0 first place, 0.5 second) | bad ordering |
| Answer correct, false refusal | exact | Does the answer match the golden one, or did it refuse needlessly? | wrong or timid answers |
| Citation hit / precision | exact | Did it cite the right document, and how many citations were right? | wrong sources |
| Faithfulness | RAGAS | Is every claim in the answer supported by the retrieved text? | hallucination |
| Answer relevancy | RAGAS | Would the answer fit the question that was asked? | evasive or off-topic answers |
| Context precision | RAGAS | Are the useful chunks ranked at the top? | badly ordered retrieval |
| Context recall | RAGAS | Does the retrieved text contain everything the golden answer says? | information retrieval missed |

---

## Phase 7 — Production Backend Hardening (4–5 days)

> **Status: 🟡 rate limiting done (see Phase 8b); prompt-injection test done (see the security checklist below).

**Goal:** The stuff that makes it "production-grade" rather than "it works on my machine."

- Centralized exception handling → consistent API error shape (started in Phase 1, extended here for edge cases surfaced by Phases 2–6).
- Rate limiting (Redis-backed token bucket, tuned per-endpoint — stricter on `/ask` than `/health`).
- Input validation (file size/type limits) and prompt-injection defenses on retrieved document content — test this deliberately, it's an interview-worthy failure mode to have handled.
- API documentation cleanup: FastAPI's auto OpenAPI/Swagger, annotated with examples and auth flows.
- Configuration management: `.env`-driven settings via Pydantic `BaseSettings`, documented in `.env.example`, no secrets committed.
- Load testing (`Locust`/`k6`) against `/ask` to get real latency numbers under concurrency — feed these numbers back into your Phase 6 latency table.

**Deliverable:** Load-test report showing p50/p95/p99 latency under concurrent load, plus a security checklist (rate limits verified, injection payloads tested and blocked).

### Security checklist: prompt injection through uploaded documents
Tests: `backend/tests/test_prompt_injection.py` (deterministic, 16 passing + 3 known gaps). They assume a fully compromised model and prove what the pipeline still guarantees. Real poisoned documents (Markdown, hidden-text HTML, CSV cell, PDF) go through the real ingestion and `/ask`.

| Status | Property |
|:---:|---|
| ✅ | Attack text reaches the prompt only inside the context block, after the rules, never in the user message |
| ✅ | Text imitating `[1]` / `[9]` cannot change the code-assigned citation numbers |
| ✅ | A compromised model cannot cite sources that were not retrieved |
| ✅ | File names never enter the prompt and come back only as inert JSON data |
| ✅ | One user's poisoned documents never reach another user; an "I am admin" memory widens nothing (authorization is the user id in the retrieval filter) |
| ✅ | Nothing retrieved means the model is never asked, so an unrelated question cannot be forced into an answer |
| ✅ | Instruction-like or sensitive facts are never stored as long-term memory |
| ✅ | Hostile HTML in a document comes back as inert `application/json` text (the frontend must escape it) |
| ⚠️ gap | Model output is not filtered: a markdown image or link to an attacker host (zero-click exfiltration) passes through |
| ⚠️ gap | The context block has no tamper-proof delimiter: document text can contain `Context:` or `END OF CONTEXT` |
| ⚠️ gap | The memory guard is a keyword regex: a paraphrased instruction ("forget all earlier rules") can be stored |
| ➖ | Whether Qwen itself resists a hidden instruction is model-dependent; covered only by one real-Qwen probe |

The gaps are written as strict `xfail` tests, so the suite flips to a loud failure the day one is fixed.

**Resume line:** *"Hardened the platform for production: per-user rate limiting, a prompt-injection test suite over poisoned documents that proves the pipeline's guarantees against a fully compromised model (with the remaining gaps documented as strict xfail tests), structured logging, and load-tested API latency."* (Claim only the items that are done.)

---

## Phase 8 — Docker 🟡

**Goal:** Containerize the stack once its behaviour is understood.

**Built (✅):** `backend/Dockerfile` and `backend/docker-compose.yml` (Postgres on host port 5433, Qdrant, Redis).

**Also built (✅):** a one-shot `migrate` service runs `alembic upgrade head` before the API and worker start, so a fresh volume or a new migration never leaves the containers on an old schema.

**Also built (✅):** health checks for `api` (`curl /health` every 15 s) and `worker` (`celery inspect ping` through the broker every 30 s). Verified in an isolated compose project: both healthy, and a frozen process turned the api `unhealthy` after 3 failed probes. Static test: `tests/test_compose_healthchecks.py`.

**Still pending (⏳):**
- `docker-compose.prod.yml`.
- Prove `docker compose up` works from a fresh clone. Inside containers `OLLAMA_BASE_URL` must be `http://host.docker.internal:11434`.

---

## Phase 9 — Rate Limiting ✅

**Goal:** Protect the expensive endpoints (`/ask` costs LLM time and, through the Gemini fallback, free-tier quota; uploads trigger embedding work) from one user, a bug or a script. Sized for the real use: the owner plus an occasional visitor.

**Built (✅):** `backend/app/core/rate_limit.py`, per user, all counters in Redis (keys `rl:*`).

| Limit | Applies to | Default (env setting) | Algorithm |
|---|---|---|---|
| Burst | `/ask` and `/ask/stream`, one shared budget | 10 per minute (`ASK_PER_MINUTE`) | token bucket |
| Daily cap | the same | 100 per UTC day (`ASK_PER_DAY`) | fixed-window counter, expires at UTC midnight |
| Uploads | `POST /documents` | 10 per hour (`UPLOAD_PER_HOUR`) | token bucket |

- Each check is one Lua script, so check-and-update is atomic and takes one Redis round trip; the bucket reads Redis's own clock.
- Check order on `/ask`: burst first, then daily, so a request refused by the burst limit never spends daily budget.
- Over a limit: HTTP 429 with `Retry-After`, `X-RateLimit-Limit` and `X-RateLimit-Reset`, decided before retrieval, the LLM or the stream start. A rejected `/ask/stream` is a real JSON 429; nothing is saved and no LLM quota is spent.
- Fails open: if Redis is down or slow (0.25 s timeout) the request goes through and a warning is logged. `RATE_LIMIT_ENABLED=false` switches it off.
- Checked: 21 new tests against real Redis (522 tests passing in total), a mutation check that the check-order test really fails when the order is swapped, and a live run over HTTP with the limit set to 2 per minute (2 answered, 3rd and 4th refused in 0.00 s with `Retry-After`, recovered after waiting).


**Resume line:** *"Added Redis-backed per-user rate limiting (token bucket and daily quota, atomic Lua scripts, 429 with Retry-After, fail-open) to protect LLM and embedding cost, verified with integration tests and a live run."*

---

## Phase 10 — CI/CD (2–3 days)

**Goal:** Demonstrate you understand the pipeline — not a DevOps deep-dive. For a strong resume signal, breadth here beats depth.

```
git push → GitHub Actions → Lint → Unit Tests → Integration Tests → Build Docker Image → Deploy

```

- GitHub Actions workflow: lint (`ruff`/`black`), unit tests (`pytest`), integration tests (spin up docker-compose services in CI, hit real endpoints).
- Build and tag the Docker image on merge to main.
- Deploy step (can be manual-trigger or auto to a staging environment — the point is the pipeline exists and works, not that it's elaborate).

**Deliverable:** A green CI badge in the README, and one PR that shows a broken test blocking merge.

**Resume line:** *"Set up a CI/CD pipeline (GitHub Actions) running lint, unit, and integration tests against containerized services before Docker image build and deploy."*

---

## Phase 11 — Frontend (1–2 weeks)

> **Status: 🟡 in progress, built in steps.** Stack decided: plain JavaScript, React 19 + Vite 8, React Router, axios, Tailwind v4, Clerk. ✅ Step 1 foundation (Clerk login, protected routes, app shell, API client with token and error handling). ⏳ Step 2 documents page, step 3 chat with streaming and citations, step 4 conversation sidebar, step 5 memory page and polish. Frontend tests, README and demo come after. Final routes: `/sign-in`, `/sign-up`, `/chat`, `/chat/:conversationId` (with the conversation sidebar), `/documents`, `/memory`.

**Goal:** A UI that demos well — by this point the backend is proven and evaluated, so the frontend is "just" surfacing it well.

Pages: `/home` , `/login`, `/register`, `/documents`, `/chat`, `/conversations`.

```
Upload PDF → Processing → Ask question → Streaming answer → [1][2][3] citations → Click citation → View source

```

- React + Tailwind (Vite). Your existing frontend skills carry most of this phase.
- Document library: upload, live status badges (pending/processing/embedded/failed), delete.
- Chat interface: streaming tokens, clickable citation cards that expand to show the source snippet and jump to the page/section.
- Conversation sidebar backed by the Phase 5 `RunnableWithMessageHistory` conversations.
- Clean empty/loading/error states — this is what actually shows in a demo video, worth the polish time.

**Deliverable:** A UI you'd screen-record for a portfolio video: upload → ask → streamed cited answer → click a citation → see the source.

**Resume line:** *"Built a React/Tailwind frontend with streaming chat, live ingestion status, and clickable citation cards linking answers back to source documents."*

---

## Phase 12 — Deployment & Final Polish (3–5 days)

**Goal:** Ship it somewhere clickable, and package the story.

```
React → production build
FastAPI → Docker
Qdrant / Postgres / Redis → Cloud

```

- Deploy: React static build (Vercel/Netlify) + FastAPI + Postgres + Redis + Qdrant on a small VPS or Fly.io/Render, with a hosted/self-hosted Qdrant instance.
- Live demo link in the README — interviewers click a link, not clone a repo.
- Record a 3–4 min demo video: upload a doc → ask a question → show a citation → show the Phase 6 eval results table.
- README as a case study: problem → architecture diagram → key decisions → eval results table → "what I'd do at scale."
- ADR-style doc: 5–6 short entries ("Why RRF over weighted fusion," "Why cross-encoder rerank," "Why LangChain over hand-rolled retrieval") — shows reasoning, not just execution.
- Final artifacts checklist: live demo, README, architecture diagram, demo video, API docs, evaluation results, ADRs, screenshots.

**Deliverable:** A public repo + live demo link + demo video, ready to paste into a resume/portfolio.

**Resume line:** *"Deployed the platform end-to-end with a live demo, documented architecture decisions (ADRs), and a recorded walkthrough tying evaluation results to design choices."*

---

## Build Order Summary

| Phase | Focus | Time | Status |
|---|---|---|---|
| 0 | Architecture & planning | 2–3 days | ✅ (README/docs ⏳) |
| 1 | FastAPI backend foundation | 3–4 days | ✅ |
| 2 | Document ingestion | 1–2 weeks | 🟡 (URLs, Markdown headers ⏳) |
| 3 | Embeddings + Qdrant | 3–5 days | ✅ |
| 4 | Advanced RAG (hybrid + rerank) | 1–2 weeks | 🟡 (paraphrase quality ⏳) |
| 5 | Generation | 4–5 days | ✅ |
| 6 | Evaluation | 1 week | 🟡 (harness ✅, bigger golden set ⏳) |
| 7 | Production hardening | 4–5 days | 🟡 (rate limiting ✅; injection test, JSON logs, load test ⏳) |
| 8 | Docker | 3–4 days | 🟡 (health checks ✅; prod compose, fresh-clone test ⏳) |
| 9 | Rate limiting | 1 day | ✅ |
| 10 | CI/CD | 2–3 days | ⏳ |
| 11 | React frontend | 1–2 weeks | 🟡 (step 1 of 5 done) |
| 12 | Deployment & polish | 3–5 days | ⏳ |

**Total: \~10–12 weeks part-time, \~7–8 weeks full-time.**

---

## Final Composite Resume Bullet

> **Enterprise Knowledge Intelligence Platform** — Built a production-grade RAG platform (FastAPI, React, **LangChain**, Qdrant, Postgres, Redis) backend-first: async ingestion via LangChain document loaders/splitters for PDF/DOCX/Markdown/URL sources, BM25 + Qdrant dense search fused with RRF, LLM-based query rewriting and paraphrase expansion, and a cross-encoder reranker — feeding a citation-backed generation pipeline with strict grounding, local-first LLM failover, and summary plus long-term conversation memory. Built a RAGAS-based evaluation pipeline (traced via LangSmith) measuring retrieval precision/recall, faithfulness, and answer relevance across configurations, using results to justify hybrid retrieval + reranking (Hit@5 0.74 → 0.93, MRR 0.55 → 0.85 vs dense-only). Containerized with Docker, CI/CD via GitHub Actions, load-tested, and deployed with a live demo.

---

### Interview Tips

- Have the Phase 6 eval results table memorized — it's the strongest single signal of engineering maturity in this project.
- Be ready to explain **why** RRF over simple score averaging, and why a cross-encoder reranker helps precision when bi-encoder recall is already decent.
- Be ready for "why LangChain instead of hand-rolling it?" — it standardizes interfaces (loaders, retrievers, chat history) so components are swappable (change embedding model, vector store, or LLM provider without rewriting the pipeline), and LCEL gives composable, streamable, traceable chains for free.
- Be honest about scale limits ("at 100k+ docs I'd move BM25 to Elasticsearch and tune Qdrant's ANN index") — shows awareness beyond the toy scale.
- Know the failure modes you tested (adversarial/out-of-scope questions, prompt injection via document content) and how the system handled them.
- Be ready to explain the phase ordering itself: backend and evaluation *before* Docker/CI/frontend means every later layer wraps something already proven correct, instead of debugging unknowns through a container or a UI.