# Enterprise Knowledge Intelligence Platform — Resume-Grade Build Roadmap

A backend-first build order: get the RAG engine correct and *measured* before touching Docker, CI, or the UI. This sequencing means you understand every service before you containerize it, and you have working, evaluated intelligence before you spend a week on React. Single-tier auth (every employee has equal access — no RBAC/admin layer). LangChain is the implementation backbone throughout.

**Target: \~12 weeks part-time, \~7–8 weeks full-time.**

---

## Phase 0 — Architecture & Planning (2–3 days)

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

**Skills exercised:** FastAPI, Pydantic, Clerk authentication, JWT verification, dependency injection, PostgreSQL, Alembic, file uploads, async patterns, authorization, and error handling.

**Deliverable:** Swagger docs showing every route, Clerk-authenticated requests successfully verified by FastAPI, authenticated users mapped to PostgreSQL, protected document endpoints working with validation, and `/retrieve` and `/ask` wired as typed stubs.

**Resume line:** *"Built a typed, async FastAPI backend integrated with Clerk authentication, JWT verification, dependency-injected user context, PostgreSQL persistence, and centralized error handling as the foundation for a production RAG service."*

---


## Phase 2 — Document Ingestion (1–2 weeks)

**Goal:** Reliable, LangChain-driven ingestion for messy real-world files.

```
Upload → Parser → Cleaning → Chunking → Metadata → Embedding → Qdrant

```

- Support PDF, DOCX, TXT, Markdown, URLs.
- **LangChain document loaders** as the standard interface so every source type returns a consistent `Document` object: 
  - PDF: `PyMuPDFLoader`/`UnstructuredPDFLoader` (OCR fallback via `pytesseract` for scanned pages)
  - DOCX: `Docx2txtLoader`/`UnstructuredWordDocumentLoader`
  - TXT/Markdown: `TextLoader`/`UnstructuredMarkdownLoader`
  - URL: `WebBaseLoader` (or a `trafilatura`-backed custom loader for cleaner extraction)
- Cleaning: strip boilerplate, headers/footers, de-hyphenate line breaks, normalize whitespace as post-load `Document` transforms.
- **LangChain text splitters** for chunking — not naive fixed-size: 
  - `RecursiveCharacterTextSplitter` (token-aware via `tiktoken` length function) as baseline
  - `MarkdownHeaderTextSplitter`/section-aware splitting for structured policy docs
  - Metadata (`doc_id, uploaded_by, page_number, section_title, chunk_index`) carried through automatically into each chunk
- Content hashing for duplicate detection — re-uploading the same file shouldn't re-embed it.
- Document status lifecycle (`pending → processing → embedded → failed`), processed as background jobs so uploads don't block the request.

**Deliverable:** Upload a batch of 20 mixed PDFs/DOCX/URLs, watch status transition async, confirm duplicate re-upload is a no-op.

**Resume line:** *"Built a fault-tolerant, async ingestion pipeline using LangChain document loaders and text splitters across PDF/DOCX/Markdown/URL sources, with content-hash deduplication and structure-aware chunking."*

---

## Phase 3 — Embeddings + Qdrant (3–5 days)

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

## Phase 4 — Advanced RAG (1–2 weeks)

**Goal:** The most important phase — this is what separates the project from a tutorial RAG app.

```
User Query
    ↓
Query Rewriting
    ↓
Multi Query
    ↓
   ┌── BM25
   │
   └── Vector Search
         ↓
    Hybrid Fusion
         ↓
      Reranker
         ↓
    Top Documents

```

- **Query rewriting**: an LCEL chain (`prompt | llm | StrOutputParser`) rewrites ambiguous/conversational queries into standalone search queries — handles follow-ups like "what about the 2023 version?"
- **Multi-query retrieval**: LangChain's `MultiQueryRetriever` generates 3–5 paraphrased queries via LLM, retrieves for each, dedupes/merges results automatically.
- **BM25**: LangChain's `BM25Retriever` (backed by `rank_bm25`) over the same corpus.
- **Vector search**: the Qdrant retriever from Phase 3.
- **Hybrid fusion**: LangChain's `EnsembleRetriever` combines BM25 + dense retrieval with Reciprocal Rank Fusion (RRF), configurable per-retriever weights.
- **Reranker**: `ContextualCompressionRetriever` wrapping a `CrossEncoderReranker` (`bge-reranker` locally, or `CohereRerank` as a drop-in) on top of the ensemble output — be ready to explain the bi-encoder recall vs. cross-encoder precision tradeoff.
- **Metadata filtering**: optional user-specified filters (date range, doc type, department, uploader) passed as `search_kwargs={"filter": ...}`.
- Compose the entire thing as one retriever chain: `rewrite → multi-query → ensemble(BM25+dense) → rerank`, exposed via `/retrieve` as a single LCEL pipeline, not scattered function calls.

**Deliverable:** `/retrieve` endpoint returns ranked chunks with per-stage scores visible (BM25 score, dense score, fused score, rerank score) for debugging and for your eval work in Phase 6.

**Resume line:** *"Built a hybrid retrieval chain in LangChain — EnsembleRetriever fusing BM25 and Qdrant dense search via RRF, LLM-based query rewriting, MultiQueryRetriever expansion, and a ContextualCompressionRetriever wrapping a cross-encoder reranker — as the core intelligence layer of the platform."*

---

## Phase 5 — Generation (4–5 days)

**Goal:** Turn retrieved context into trustworthy, cited, streamed answers.

```
Retriever → Context Builder → Prompt → LLM → Answer

```

- Context builder: assemble top reranked chunks into a token-budgeted prompt (truncate/prioritize by score, dedupe overlapping chunks) as an LCEL `RunnableLambda` step.
- Prompt template (`ChatPromptTemplate`) enforcing: answer only from retrieved context, cite sources inline (`[1]`, `[2]`), explicitly say "I don't know" when context is insufficient — test deliberately with out-of-scope questions.
- Full chain composed via LCEL: `retriever_chain → context_builder → prompt → llm → StrOutputParser`.
- Citation mapping: map `[1]` back to `(doc_id, page, section)` from `Document.metadata`, returned as structured metadata for the frontend to render as clickable source cards.
- Streaming via `.astream()`/`.stream()` on the LCEL chain, piped through SSE or WebSocket.
- Conversation memory: `RunnableWithMessageHistory` backed by a custom `BaseChatMessageHistory` reading/writing Postgres; condensed history feeds back into the Phase 4 query-rewrite step for follow-ups.

At this point you have a **fully working RAG backend** — before Docker, before CI/CD, before frontend.

**Deliverable:** `curl` a question at `/ask`, get a streamed, cited, grounded answer; ask an out-of-scope question, get an honest "I don't know."

**Resume line:** *"Implemented citation-backed streaming generation as a composed LCEL chain with strict grounding and RunnableWithMessageHistory-managed conversation memory — model abstains when retrieved context is insufficient."*

---

## Phase 6 — Evaluation (1 week) — *do this before the frontend*

**Goal:** Prove the system works with numbers. This is what turns "I made a RAG chatbot" into "I engineered and evaluated a retrieval system" — the single biggest differentiator on your resume.

- Build a **golden eval set**: 50–100 question/answer pairs with known-correct source chunks, spanning easy/hard/out-of-scope questions, against your own ingested docs.
- Integrate **RAGAS** to compute: 
  - **Retrieval Precision\@K / Recall\@K**
  - **Context Precision / Context Recall**
  - **Faithfulness** (is the answer actually grounded, catches hallucination)
  - **Answer Relevance**
- Also track: **latency** (retrieval / rerank / generation, p50/p95), **token usage**, **cost per query**.
- Run the eval across three configurations and compare: 
  - Dense only
  - Dense + BM25
  - Dense + BM25 + Reranker
- Wire **LangSmith** to trace every query end-to-end (retrieved chunks, scores, prompt, tokens, latency) — makes the eval story concrete and debuggable.
- Output a results table/report you can drop straight into your README and your interview answers.

**Deliverable:**

| Config Retrieval Precision\@5 Recall\@5 Faithfulness Answer Relevance p95 Latency  |      |      |      |      |      |
| ---------------------------------------------------------------------------------- | ---- | ---- | ---- | ---- | ---- |
| Dense only                                                                         | 0.61 | 0.58 | 0.79 | 0.83 | 1.2s |
| + BM25 hybrid                                                                      | 0.71 | 0.68 | 0.84 | 0.86 | 1.4s |
| + Reranker                                                                         | 0.84 | 0.79 | 0.91 | 0.90 | 1.9s |

**Resume line:** *"Built a RAGAS-based evaluation pipeline (retrieval precision/recall, faithfulness, answer relevance, latency, cost) traced via LangSmith, and used it to justify hybrid retrieval + reranking with data — improving faithfulness from 0.79 to 0.91."*

---

## Phase 7 — Production Backend Hardening (4–5 days)

**Goal:** The stuff that makes it "production-grade" rather than "it works on my machine."

- Structured logging (JSON logs, request IDs, correlate across the ingestion/retrieval/generation path).
- Centralized exception handling → consistent API error shape (started in Phase 1, extended here for edge cases surfaced by Phases 2–6).
- Rate limiting (Redis-backed token bucket, tuned per-endpoint — stricter on `/ask` than `/health`).
- Input validation (file size/type limits) and prompt-injection defenses on retrieved document content — test this deliberately, it's an interview-worthy failure mode to have handled.
- API documentation cleanup: FastAPI's auto OpenAPI/Swagger, annotated with examples and auth flows.
- Configuration management: `.env`-driven settings via Pydantic `BaseSettings`, documented in `.env.example`, no secrets committed.
- Load testing (`Locust`/`k6`) against `/ask` to get real latency numbers under concurrency — feed these numbers back into your Phase 6 latency table.

**Deliverable:** Load-test report showing p50/p95/p99 latency under concurrent load, plus a security checklist (rate limits verified, injection payloads tested and blocked).

**Resume line:** *"Hardened the platform for production: structured logging, rate limiting, prompt-injection input sanitization, and load-tested API latency under concurrent users."*

---

## Phase 8 — Docker (3–4 days)

**Goal:** Containerize only once every service's behavior is already understood — you're encoding known-good behavior, not debugging blind inside a container.

- Containerize: FastAPI, PostgreSQL, Redis, Qdrant.
- `Dockerfile` (multi-stage build for the FastAPI image), `docker-compose.yml`, `.env.example`.
- `docker compose up` brings up the full backend stack cleanly from a fresh clone.
- Health checks per service in the compose file.
- `docker-compose.prod.yml` variant for later deployment (leaner image, no dev volumes/reload).

**Deliverable:** Fresh clone → `docker compose up` → full backend healthy and answering `/ask` within minutes, no manual setup steps.

**Resume line:** *"Containerized the full backend stack (FastAPI, Postgres, Redis, Qdrant) with multi-stage Docker builds and compose-based orchestration for reproducible local and production environments."*

---

## Phase 9 — CI/CD (2–3 days)

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

## Phase 10 — Frontend (1–2 weeks)

**Goal:** A UI that demos well — by this point the backend is proven and evaluated, so the frontend is "just" surfacing it well.

Pages: `/login`, `/register`, `/documents`, `/chat`, `/conversations`.

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

## Phase 11 — Deployment & Final Polish (3–5 days)

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

| Phase Focus Time  |                                |           |
| ----------------- | ------------------------------ | --------- |
| 0                 | Architecture & planning        | 2–3 days  |
| 1                 | FastAPI backend foundation     | 3–4 days  |
| 2                 | Document ingestion             | 1–2 weeks |
| 3                 | Embeddings + Qdrant            | 3–5 days  |
| 4                 | Advanced RAG (hybrid + rerank) | 1–2 weeks |
| 5                 | Generation                     | 4–5 days  |
| 6                 | Evaluation                     | 1 week    |
| 7                 | Production hardening           | 4–5 days  |
| 8                 | Docker                         | 3–4 days  |
| 9                 | CI/CD                          | 2–3 days  |
| 10                | React frontend                 | 1–2 weeks |
| 11                | Deployment & polish            | 3–5 days  |

**Total: \~10–12 weeks part-time, \~7–8 weeks full-time.**

---

## Final Composite Resume Bullet

> **Enterprise Knowledge Intelligence Platform** — Built a production-grade RAG platform (FastAPI, React, **LangChain**, Qdrant, Postgres, Redis) backend-first: async ingestion via LangChain document loaders/splitters for PDF/DOCX/Markdown/URL sources, an EnsembleRetriever fusing BM25 and Qdrant dense search via RRF, LLM-based query rewriting, MultiQueryRetriever expansion, and a ContextualCompressionRetriever wrapping a cross-encoder reranker — feeding a citation-backed streaming generation chain with strict grounding and RunnableWithMessageHistory-managed conversation memory. Built a RAGAS-based evaluation pipeline (traced via LangSmith) measuring retrieval precision/recall, faithfulness, and answer relevance across configurations, using results to justify hybrid retrieval + reranking and improving faithfulness from 0.79 to 0.91. Containerized with Docker, CI/CD via GitHub Actions, load-tested, and deployed with a live demo.

---

### Interview Tips

- Have the Phase 6 eval results table memorized — it's the strongest single signal of engineering maturity in this project.
- Be ready to explain **why** RRF over simple score averaging, and why a cross-encoder reranker helps precision when bi-encoder recall is already decent.
- Be ready for "why LangChain instead of hand-rolling it?" — it standardizes interfaces (loaders, retrievers, chat history) so components are swappable (change embedding model, vector store, or LLM provider without rewriting the pipeline), and LCEL gives composable, streamable, traceable chains for free.
- Be honest about scale limits ("at 100k+ docs I'd move BM25 to Elasticsearch and tune Qdrant's ANN index") — shows awareness beyond the toy scale.
- Know the failure modes you tested (adversarial/out-of-scope questions, prompt injection via document content) and how the system handled them.
- Be ready to explain the phase ordering itself: backend and evaluation *before* Docker/CI/frontend means every later layer wraps something already proven correct, instead of debugging unknowns through a container or a UI.