# KnowledgeOS

**Chat with your own documents and get answers you can check.** Every answer points to the exact passage it came from.

Upload PDFs, Word, PowerPoint, Excel, CSV, Markdown or HTML files into a chat and ask questions in plain language. KnowledgeOS finds the right passages with hybrid search, reranks them, and streams back an answer with numbered citations. Click one and you see the source text. It runs entirely on free, local models, so it costs ₹0.

![Python](https://img.shields.io/badge/Python-3.13-0f6b5c)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-0f6b5c)
![React](https://img.shields.io/badge/React-19-0f6b5c)
![Backend tests](https://img.shields.io/badge/backend%20tests-653%20passing-0f6b5c)
![Coverage](https://img.shields.io/badge/coverage-95%25-0f6b5c)
![Frontend tests](https://img.shields.io/badge/frontend%20tests-119%20passing-0f6b5c)

![A cited answer with its source passage open](docs/screenshots/chat-light.png)

<!-- Demo GIF: record a 20-30 s clip (upload -> ask -> click a citation) and put it here as docs/demo.gif -->

---

## Contents

- [What it does](#what-it-does)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Results](#results)
- [Engineering decisions](#engineering-decisions)
- [Security](#security)
- [Tech stack](#tech-stack)
- [Running it locally](#running-it-locally)
- [Project structure](#project-structure)
- [Limitations and roadmap](#limitations-and-roadmap)

## What it does

- **Answers with sources.** Each claim carries a `[n]` chip. It opens the passage, the file name and the page, slide or spreadsheet rows. If the documents don't contain the answer, it says so instead of guessing.
- **Documents belong to a chat.** Files you add to a conversation are the only ones its questions search, so two projects never mix.
- **Streaming.** The answer appears word by word, and you can stop it at any time.
- **Remembers you.** Short facts about you, like your role, projects and preferences, carry across all your chats. Long chats are summarised so nothing is lost. You can see, add and delete every fact.
- **Everyday polish.** Chats are grouped by day and can be renamed or deleted. Uploads show live status. Greetings get instant answers. It has dark mode and a phone layout.
- **Free to run.** Embeddings, reranking and the LLM (Qwen3 8B through Ollama) all run locally. Gemini is an optional cloud fallback.

## Screenshots

| Sign in | Start a chat |
|---|---|
| ![Sign-in page](docs/screenshots/sign-in.png) | ![Empty chat with a question being typed](docs/screenshots/new-chat.png) |
| **What it remembers about you** | **Dark mode** |
| ![Memory dialog](docs/screenshots/memory.png) | ![Dark mode with a cited answer](docs/screenshots/chat-dark.png) |

<p align="center"><img src="docs/screenshots/phone.png" width="280" alt="Phone layout: the source opens as a bottom sheet"><br><em>On a phone the source opens as a bottom sheet.</em></p>

## Architecture

![KnowledgeOS architecture](docs/architecture.png)

**Reading a document** runs in the background:
1. `POST /documents` checks the type, the 20 MB limit and duplicates (by hash).
2. It stores the file and queues a Celery task through Redis.
3. The worker loads the file, runs OCR on scanned pages (Tesseract), cleans the text and splits it into 512-token chunks. Spreadsheet chunks never span two sheets.
4. Each chunk is embedded twice, as a dense `bge-large` vector and a sparse BM25 vector, and stored in Qdrant.
5. The chat chip moves from *Uploading* to *Reading* to ready.

**Answering a question** (`POST /ask/stream`):
1. Greetings and introductions are answered at once, with no model call.
2. A follow-up is rewritten into a standalone question using the chat history.
3. Hybrid search: dense and BM25 results are fused with reciprocal rank fusion inside Qdrant. They're filtered to **your user id** and **this chat's documents**.
4. A cross-encoder (`bge-reranker-base`) keeps the best 5 passages.
5. The prompt is built within a 3,000-token budget, with numbered sources marked as untrusted, plus your memory and the chat summary.
6. The LLM streams tokens over server-sent events. Citation numbers are mapped back to their real sources in code, and the turn is saved with its citations.

**Memory** has two layers:
- **Inside one chat:** once the unsummarised messages pass 1,500 tokens, the older ones are folded into a rolling summary.
- **Across all chats:** up to 15 facts in a LangGraph `PostgresStore`. The LLM learns them when you leave a chat, or every 6 answers. Introductions such as "myself Dishant" are stored instantly by a rule-based parser.

## Results

### Retrieval and answer quality

Measured with the evaluation harness in [`backend/eval/`](backend/eval/README.md): 13 synthetic documents, 121 chunks and a 45-question golden set (42 answerable, 3 out of scope). Local Qwen3 8B is both generator and judge.

| Metric | Dense only | Hybrid | **Hybrid + rerank** (used) |
|---|---|---|---|
| Hit@5: all needed passages found | 0.74 | 0.93 | **0.93** |
| MRR: right passage near the top | 0.55 | 0.78 | **0.85** |
| Answers correct | 0.74 | 0.93 | **0.93** |
| False refusals | 0.24 | 0.07 | **0.05** |
| Cites an expected document | 0.74 | 0.90 | **0.93** |
| Refuses out-of-scope questions | 1.00 | 1.00 | **1.00** |
| RAGAS faithfulness | 0.80 | 0.75 | **0.82** |
| RAGAS context precision | 0.52 | 0.69 | **0.74** |

Adding BM25 to dense search fixes most misses: answers correct go from 0.74 to 0.93. Reranking then puts the right passage first more often (MRR 0.78 to 0.85) and lowers false refusals. RAGAS scores come from a small local judge on a 20-question sample, so they're useful for comparing columns, not as absolute numbers.

### Tests

| | Tests | What they cover |
|---|---|---|
| **Backend** (pytest) | **653 passing, 95% line coverage** | Mostly integration tests against **real** Postgres, Qdrant and Redis, the real embedding and reranking models, and a real Celery worker end to end. The LLM is faked for determinism, and a smaller set runs against real local Qwen. Includes auth, rate limits, ingestion of every file type, retrieval, citations, memory and prompt injection. |
| **Frontend** (Vitest + Testing Library) | **119 passing, under 1 s** | Error mapping, the SSE stream parser (split chunks, cut-off streams, abort), components, upload and conversation hooks (with fake timers), and an integration test of the whole chat screen. The API and Clerk are mocked. |

## Engineering decisions

Each one was measured or argued, not assumed:

- **Hybrid search instead of vectors alone.** Dense embeddings miss exact terms such as policy names, codes and numbers, and BM25 catches them. Fusion happens inside Qdrant (RRF), so it's still one query.
- **Removed parent/child chunking.** It looked good on paper, but the expanded parent chunks overflowed the 3,000-token prompt budget: 41 of 45 questions lost passages before the LLM saw them. Plain 512-token chunks did better.
- **Query paraphrasing is off by default.** Generating 4 paraphrases per question cost about 6 s (retrieval went from 8.4 s to 2.3 s without them) with no gain in Hit@5 (0.93 vs 0.93). The history-aware rewrite stays, because follow-up questions need it.
- **Streaming over `fetch`, not `EventSource`.** `EventSource` can only send GET and can't add an `Authorization` header, and axios can't stream in the browser. The stream is read with a `ReadableStream` reader, and HTTP errors before the first token are still real status codes.
- **Authorization lives in the search filter.** Every Qdrant query is filtered by the caller's user id and the chat's document ids. A test proves that a poisoned memory claiming "user is admin" can't widen it.
- **Citations are assigned by code, not by the model.** The model only sees `[1]..[n]`. Numbers are mapped back to real sources afterwards, so it can't invent a source that wasn't retrieved.
- **Leftover refusals are kept out of the prompt.** A real bug, found with local Qwen: one early "I don't know" in the history made every later answer refuse (3/3). Refused and canned turns are now left out of the model's history (3/3 answered).
- **Token-bucket rate limits in Redis.** 10 questions per minute and 10 uploads per hour use a token bucket. A fixed-window counter caps questions at 100 per day. Each check is an atomic Lua script, and the limiter fails open if Redis is down.
- **Random UUIDs in URLs.** Conversations are addressed by a random UUID, never by the internal integer id, so ids can't be guessed or counted.
- **Local-first LLM with a fallback.** Ollama (Qwen3 8B) is the primary model. LangChain's `with_fallbacks` switches to Gemini on errors. No model available gives a clear 503; an exhausted quota gives 429.

## Security

What the pipeline guarantees, proven by deterministic tests that assume a **fully compromised model**:

- Text in a document (including hidden HTML text, CSV cells and PDF text) only ever lands inside the prompt's context block, after a guard sentence. It never lands in the user's message.
- Citation markers written inside a document can't change the code-assigned markers, and the model can't cite sources that weren't retrieved.
- File names never enter the prompt.
- One user's documents never reach another user, whether through the prompt, citations or `/retrieve`.
- Secrets and instruction-like text are refused as memory facts.
- The frontend renders answers and snippets as plain text, never as HTML or markdown.
- Clerk JWTs are verified on every route. The only anonymous routes are `/health` and the signed Clerk webhook. CORS uses an allow-list. Raw error text from failed documents is never returned to the client.

Known gaps, documented as strict `xfail` tests so a fix shows up immediately:
1. Model output isn't filtered: a markdown image link to an attacker's server would pass through the API. The bundled frontend is safe because it never renders markdown.
2. The context block has no tamper-proof delimiter.
3. The memory guard is a keyword filter, not a classifier.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite 8, Tailwind CSS v4, React Router 7, axios, Clerk React; Vitest and Testing Library |
| API | FastAPI, Pydantic, SQLAlchemy 2, Alembic |
| Background work | Celery with a Redis broker |
| Search | Qdrant (dense and sparse vectors, RRF fusion); FastEmbed with `BAAI/bge-large-en-v1.5`, BM25 and `BAAI/bge-reranker-base` |
| Document parsing | LangChain loaders, PyMuPDF, Unstructured, Tesseract OCR |
| LLM | Qwen3 8B through Ollama (local), Google Gemini (optional fallback), LangChain |
| Memory | Postgres (conversation summaries), LangGraph `PostgresStore` (long-term facts) |
| Auth | Clerk (JWT verified with JWKS, svix-signed webhooks) |
| Quality | pytest (653 tests), RAGAS evaluation harness, LangSmith tracing (opt-in) |
| Infrastructure | Docker Compose (Postgres, Qdrant, Redis, migrations, API, worker, health checks) |

## Running it locally

**You need:**
- Python 3.13
- Node 18+
- Docker Desktop
- `brew install tesseract libmagic` (on macOS)
- [Ollama](https://ollama.com) with `ollama pull qwen3:8b`
- A free [Clerk](https://clerk.com) application

**1. Configure.** Copy the example files and fill them in. Each variable is explained in its file.

```bash
cp backend/.env.example backend/.env      # database, Qdrant, Redis, Clerk JWKS/issuer, LLM provider
cp frontend/.env.example frontend/.env    # VITE_API_URL and your Clerk publishable key (pk_...)
```

In the Clerk dashboard, allow `http://localhost:5173`.

**2. Backend.** Postgres, Qdrant and Redis run in Docker; the API and worker run locally.

```bash
python3.13 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend
docker compose up -d postgres qdrant redis       # Postgres on host port 5433
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --reload                              # API on :8000
../.venv/bin/celery -A app.worker.celery_app worker --loglevel=info     # in a second terminal
```

The first question after a start loads about 3 GB of models, which takes around 30 s.

To run everything in containers instead, use `docker compose up -d` in `backend/`. A one-shot `migrate` service applies the migrations before the API and worker start. Inside containers, set `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

**3. Frontend**

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

**4. Tests and evaluation**

```bash
cd backend && ../.venv/bin/python -m pytest -q    # uses an isolated <db>_test database, Redis DB 15, its own Qdrant collection
cd frontend && npm test                           # Vitest
cd backend && ../.venv/bin/python -m eval.run     # full evaluation (about an hour with local models), see backend/eval/README.md
```

## Project structure

```
backend/
  app/
    routers/        HTTP routes (ask, documents, conversations, memory, users, webhooks)
    services/       business logic (ask flow, uploads, conversations, social messages, memory steps)
    ingestion/      loaders -> OCR -> cleaning -> chunking -> embeddings -> Qdrant
    retrieval/      query rewrite, hybrid search, reranking
    augmentation/   context builder and prompt
    generation/     LLM factory with fallback, streaming, citations, summaries
    memory/         long-term memory store and consolidation
    core/           settings, Clerk auth, rate limits, CORS, tracing
    db/models/      SQLAlchemy models        worker/  Celery app and tasks
  alembic/          migrations
  tests/            653 tests (integration-first)
  eval/             golden set, metrics, RAGAS scoring, reports
frontend/
  src/
    api/            axios client, SSE stream reader, error mapping
    features/       chat, documents, memory (components, hooks, tests next to them)
    auth/ theme/ components/ layout/ pages/ lib/
docs/               architecture diagram and screenshots
```

## Limitations and roadmap

**Limitations:**
- 20 MB per file.
- Embedding runs on the CPU: a 40-page PDF takes about a minute, and a 1,000-page one about 20 minutes.
- An answer takes about 7–12 s on a laptop with local Qwen.
- The Gemini free tier allows only a few requests per day.
- There's no view of the full document yet; citations show a 600-character passage.

**Next:**
- CI with GitHub Actions
- A public deployment (Cloudflare Tunnel or a free VM)
- A demo video
- Playwright end-to-end tests
- Closing the three known security gaps
