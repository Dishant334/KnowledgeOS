# KnowledgeOS

Backend-only AI knowledge management / RAG application. Roadmap: `Plan.md` (intended architecture, not proof of implementation).

**Stack:** Python 3.13 · FastAPI · PostgreSQL · SQLAlchemy · Alembic · Clerk · Qdrant · Redis · Celery · LangChain · FastEmbed

## Mandatory approval workflow

The user must approve before ANY code change. For every stage:

1. Inspect only relevant files.
2. Identify problems.
3. Propose a concise implementation plan.
4. List exact files to modify.
5. Explain important changes and risks.
6. **STOP and wait for explicit approval.**
7. Implement only approved changes.
8. Run relevant tests.
9. Report actual results.
10. **STOP before the next stage.**

Never modify code without explicit approval. If work outside the approved scope becomes necessary, stop and request approval.

## Development rules

- Prefer fixing existing code over rewriting; preserve architecture and conventions.
- Avoid unnecessary dependencies.
- Don't inspect unrelated files or repeat full repository audits.
- Never delete data, reset databases, or drop tables/volumes without explicit permission.
- Use safe, incremental Alembic migrations.
- Never expose secrets (`backend/.env` is git-ignored; never print its values).
- Never claim tests passed unless actually executed; clearly distinguish mocked vs integration tests.
- Keep explanations concise.

## Local development (macOS)

Postgres, Qdrant and Redis run via Docker Compose; FastAPI runs locally. Run everything from `backend/` (Settings reads `.env` relative to CWD).

```bash
export PATH="$HOME/.docker/bin:$PATH"            # Docker Desktop CLI is not on PATH by default
cd backend
docker compose up -d postgres qdrant redis       # Postgres on host port 5433
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --reload
../.venv/bin/celery -A app.worker.celery_app worker --loglevel=info   # ingestion worker
../.venv/bin/python -m pytest -q                 # uses isolated DB <dev_db>_test
```

- venv: repo-root `.venv` (Python 3.13). Deps: `backend/requirements.txt`, dev: `backend/requirements-dev.txt`.
- System deps: `brew install tesseract libmagic`.
- Env vars documented in `backend/.env.example`.
- 13 `__pycache__/*.pyc` files are tracked in git; use `PYTHONDONTWRITEBYTECODE=1` to avoid dirtying them.

## Layout (`backend/app/`)

`routers/` → `services/` → `db/models/` · `core/` (config, Clerk) · `dependencies/auth.py` (`get_current_user`) · `ingestion/` (loaders → OCR → cleaning → chunking → embedding/Qdrant) · `retrieval/` · `augmentation/` · `generation/` · `worker/` (Celery) · tests in `backend/tests/`.

## Current state

- **Stage 1 (done):** environment & dependencies verified.
- **Stage 2 (done):** Clerk auth repaired; 42 tests passing (mocked JWKS/svix + isolated Postgres test DB). Real Clerk session login still manually unverified.
- **Stage 3 (done):** documents schema repaired (migration `5085fd428cba`): storage/hash/error columns, per-user dedup (`uq_documents_user_id_document_hash`), `document_blobs` keyed by `document_id` with ON DELETE CASCADE. `alembic/env.py` ignores the library-owned `message_store` table. 60 tests passing.
- **Stage 4 (done):** ingestion pipeline repaired end-to-end: authenticated upload → Postgres bytes → Celery dispatch (`send_task` by name) → real worker → load/OCR/clean/chunk → bge-large + BM25(IDF) → Qdrant → `ready`. Status `pending → processing → ready | failed` (back to `pending` while retrying). Advisory-lock duplicate control, `acks_late` recovery, per-document vector deletion. 166 tests passing, incl. real-worker e2e (`tests/test_worker_e2e.py`).
- **Test isolation:** Postgres `<dev_db>_test`, Redis DB 15, Qdrant collection `knowledgeos_test_chunks` (all set in `tests/conftest.py`).
- **macOS note:** `celery_app.py` sets `FORKED_BY_MULTIPROCESSING=1` on spawn platforms; without it every prefork task crashes.
- **Stage 5 (done, pending user review of diffs):** retrieval repaired and `/retrieve` + `/ask` mounted. Flow: `retrieval/orchestrator.retrieve()` = optional LLM rewrite/paraphrases → hybrid search (dense + BM25, Qdrant RRF) filtered to `uploaded_by=<current user>` → merge → cross-encoder rerank (cached) → parent expansion. Models load lazily (`get_search_store`, `get_reranker`). `/ask` uses the `messages` table for history (not `message_store`). 244 tests passing (incl. real local Qwen).
- **LLM (done):** `app/generation/llm.py::get_llm()` builds `LLM_PROVIDER` (primary) and `LLM_FALLBACK_PROVIDER` (used automatically on error/quota) via LangChain `with_fallbacks`. Providers: `ollama` (local Qwen3 8B, `ollama pull qwen3:8b`, dev/offline/private) and `gemini` (cloud, free tier, `GEMINI_API_KEY` from Google AI Studio, deployable at ₹0). **Local-first:** `LLM_PROVIDER=ollama`, `LLM_FALLBACK_PROVIDER=gemini` (fallback sends document text to Google; leave empty to stay local). Deployed host without Ollama: `LLM_PROVIDER=gemini`, fallback empty. Full architecture is kept (local bge-large + BM25 + cross-encoder); live access via Cloudflare Tunnel or an Oracle free VM, not a shrunken app. No provider working → `/ask` 503. LLM quota errors → `/ask` 429. Real Gemini calls are opt-in in tests (`RUN_GEMINI_TESTS=1`); tests otherwise use fakes or local Qwen. Public demo: use non-sensitive documents (Gemini free tier prompts may be used by Google).
- **Augmentation/generation (audited, fixed):** refusal detection handles wording variants and curly apostrophes (`is_refusal`); an empty context (all chunks over budget) or blank model answer returns the standard refusal without/after no useful LLM call; `/ask` returns only the citations the answer uses (`only_cited`, handles `[1]`, `[1, 2]`, `[1][3]`; falls back to all sources if none cited); HTML headings give `section_title`. 299 tests passing (incl. real Qwen).
- **Cleanup (done):** removed unused `generation/memory.py` and `augmentation/prompt_template.py`; the app starts with no service running (all connections are lazy). Legacy `message_store` table is left in the DB (ignored by Alembic). Prompt says document text is untrusted; spreadsheet citations carry `sheet_name`/`row_start`/`row_end` and spreadsheet chunks never span two sheets.
- **Conversation memory (done):** old messages are never dropped; when the not-yet-summarized messages pass 1500 tokens (`HISTORY_MAX_TOKENS`), the older ones are folded into a rolling summary stored on `conversations.summary` (+ `summarized_until_message_id`, migration `7c1e9a4b2d03`) by `services/ask._summarize_if_needed` / `generation/summary.py`, after the answer is saved (a failure is logged and retried next question). The prompt gets the summary + the newest ~800 tokens of raw messages; the rewriter sees both. `trim_history` is only a last-resort safety net. Costs one extra LLM call each time the threshold is crossed (counts against the Gemini free quota). Summaries are not returned by any endpoint yet.
- **Long-term memory (done):** facts about a user that persist across ALL their conversations, stored with LangGraph's `PostgresStore` (package `langgraph-checkpoint-postgres`) in our Postgres: tables `store`/`store_migrations` (created on first use, ignored by Alembic), namespace `("user_memory", user_id)`, max 15 facts x 200 chars (`app/memory/store.py`). When a conversation's summary updates, `app/memory/consolidate.py` asks the LLM to merge the important durable facts (role, office, preferences, ongoing projects; not document facts, not secrets) into the user's memory; sensitive or instruction-like text is blocked in code. Every `/ask` (any conversation) puts the user's memory into the prompt as background only (capped at 500 tokens) and into the rewriter text. Users manage it with `GET/POST /memory`, `DELETE /memory/{id}`, `DELETE /memory`; the Clerk `user.deleted` webhook wipes it. Memory failures never fail `/ask`. Conversations that never get long enough to be summarized add nothing (use `POST /memory`). 395 tests passing.
- **Gotcha:** `requirements.txt` was re-saved as UTF-16 once by an outside tool; keep it UTF-8 (`file backend/requirements.txt`).
- **Full live verification (2026-11-04):** black-box run over HTTP (real uvicorn + Celery worker + Postgres + Qdrant + Redis + models + local Qwen; only Clerk's JWKS faked) on 10 mixed-format documents: 58/59 checks passed; 408 tests passing. It found and fixed: ParentExpander merged different PDF pages (parent_id repeats per page; now keyed by section text), refusal wording gaps ("does not provide information", "don't mention"), retired default Gemini model (now `gemini-3.5-flash`), silent provider failures (now logged). Findings: hybrid retrieval Hit@5 1.00 / MRR 0.95 on a 23-chunk corpus (too small to separate configs); `/ask` p50 ~4 s local, `/retrieve` p50 ~0.2 s without LLM (~2.5 s when the LLM makes query paraphrases); first request after a restart loads ~3 GB of models (~30 s).
- **Gemini free tier is tiny for this key: 20 requests/day per model** (each `/ask` uses 2 LLM calls) - treat it as emergency fallback, not a deployable primary; opt-in Gemini tests consume it.
- **Docker gaps:** nothing runs `alembic upgrade head` in the container, no API/worker healthchecks, `OLLAMA_BASE_URL` must be `http://host.docker.internal:11434` inside containers.
- **Observability (fixed):** LangSmith tracing existed only as `LANGSMITH_*` lines in `.env` that nothing exported, so it never ran. Now `Settings` has the `langsmith_*` fields and `export_tracing_environment()` (app/core/config.py) puts them in `os.environ`; opt-in (needs switch + key), tests force it off. `app/core/tracing.py` adds `@traceable` on ask / retrieve / hybrid_search / rerank / generate_answer with safe input summaries (no llm object, db session, user id or raw history). GOTCHA: `@traceable` treats any kwarg named `config` as a LangChain RunnableConfig, so `retrieve()` takes `retrieval_config`. Uploads questions/passages/answers to LangSmith cloud when on (use LANGSMITH_HIDE_INPUTS/OUTPUTS for privacy).
- **Evaluation harness (done): `backend/eval/`** (read `eval/README.md`): synthetic 13-document corpus + 45-question golden set, 3 retrieval configs (dense / hybrid / hybrid+rerank), exact metrics (Hit/Recall/Precision@5, MRR, answer correctness, citations, refusals) + RAGAS 0.4.3 (faithfulness, answer relevancy, context precision/recall) with the local Qwen judge on a stratified 20-question subset. Run `python -m eval.run` (about an hour); report in `eval/results/latest.md`. Deps: `requirements-eval.txt` (RAGAS needs langchain-core>=1.7, now pinned). `eval/compat.py` shims a RAGAS/langchain-community import mismatch. Use a NEW judge object per `evaluate()` call (event-loop gotcha).
- **Parent/child chunking REMOVED** (ParentChildStrategy, ParentExpander, `use_parent_expansion`): expanded chunks blew the 3000-token prompt budget (41/45 questions lost chunks; Hit 0.95 retrieved vs 0.86 seen) and every chunk carried a copy of its parent in the payload. PDFs/DOCX/TXT/MD now use the plain recursive 512-token splitter. `ContextBuilder` now reports `used_chunks` (what really reached the LLM). 441 tests passing.
- **Open:** paraphrase questions are the weak spot (Hit@5 0.50 in all configs): try LLM query expansion in the eval, smaller chunks, a stronger embedder; add real `GEMINI_API_KEY` and verify live; untrack the 13 committed `__pycache__/*.pyc` files; streaming; citations aren't persisted with messages; no endpoint shows conversation summaries.
