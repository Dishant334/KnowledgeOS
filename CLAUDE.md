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
- **Open:** retrieve/ask routers not mounted (retrieval/generation stage); `retrieval/orchestrator.py` still builds models at import; reranker cache_dir; no LLM wired.
