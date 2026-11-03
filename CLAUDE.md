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
- **Cleanup (done):** removed unused `generation/memory.py` (second history table + import-time Postgres connection) and `augmentation/prompt_template.py`; `langchain-postgres` dropped from requirements, `psycopg` moved to dev requirements (only tests use it). The app now starts with no service running. Legacy `message_store` table is left in the DB (ignored by Alembic). History is trimmed to 1500 tokens (`trim_history`, always starts with a user message); prompt says document text is untrusted; spreadsheet citations carry `sheet_name`/`row_start`/`row_end` and spreadsheet chunks never span two sheets. 311 tests passing.
- **Gotcha:** `requirements.txt` was re-saved as UTF-16 once by an outside tool; keep it UTF-8 (`file backend/requirements.txt`).
- **Open:** add a real `GEMINI_API_KEY` and verify live; untrack the 13 committed `__pycache__/*.pyc` files; streaming; `generation/memory.py` (second history table, connects at import, used by `main.py` lifespan) is now unused by requests and can be removed; citations aren't persisted with messages.
