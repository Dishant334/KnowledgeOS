# KnowledgeOS: "Chat with a Codebase" Plan

A step-by-step plan to add code question-answering (C, C++, Java, Python, JavaScript) to KnowledgeOS. Written to be **followed slowly by Claude Code with the owner learning at every step**. It extends `Plan.md` (the original roadmap) and respects `CLAUDE.md` (mandatory approval workflow).

> Status legend: ⏳ not started · 🟡 in progress · ✅ done. Update after each stage.

---

## 0. How Claude Code must work on this plan (read first)

These rules are in addition to `CLAUDE.md`. If they conflict, `CLAUDE.md` wins.

1. **One stage at a time. Never start the next stage** without the owner saying so.
2. **Teach before you code.** At the start of each stage, in plain language and in this order:
   - *What we are building and why* (3-5 sentences).
   - *The one new concept to learn* (named in each stage below). Explain it with a tiny example, not a lecture.
   - *Exact files to change* and a one-line reason per file.
   - *Risks* and *what could break*.
   - Then **STOP and wait for approval** (`CLAUDE.md` step 6).
3. **Small diffs.** Prefer many small edits over one big one. Show the key lines of each change and explain them in one or two sentences ("this line stops the cleaner from touching code because...").
4. **Tests first when possible.** Write the failing test, show it fail, then make it pass. Say whether each test is a unit test, an integration test (real Postgres/Qdrant/Redis) or mocked. Never claim a test passed unless it was run.
5. **Measure, don't assume.** From Stage 5 on, every retrieval change is judged by the code eval numbers, not by feeling. Report numbers honestly, including when a change does not help.
6. **After each stage**, report in this format: *What changed · Test results (counts, mocked vs integration) · What I did NOT verify · What the owner should try by hand · What was learned*. Then one commit per stage (owner decides when to commit).
7. **Stop and ask** if work outside the approved scope becomes necessary, a migration is needed that is not in the stage, or a dependency must be added.
8. **Never** print `.env` values, delete data, reset databases, or drop volumes.

---

## 1. Goal and scope

**Goal:** a user starts a *Codebase* chat, uploads a project (a zip, or a few source files), and asks questions about it. Answers cite `path/to/file.py · lines 40-72`.

**In scope (v1):**
- Project types: plain code, **MERN** apps (Mongo/Express/React/Node), **Flask/Python** apps, and **AI/ML** projects (scripts plus Jupyter notebooks and small datasets). See the file tiers in section 2.5.
- Languages (understood by structure): Python, JavaScript/JSX, TypeScript/TSX, Java, C, C++. Everything else useful in a project (HTML, CSS, JSON, YAML, SQL, shell, Markdown, CSV, notebooks) is supported as text, see 2.5.
- Sources: single/multiple source files, a **zip** of a project, and a **"Choose folder"** button that zips in the browser.
- Mode per chat (`docs` or `code`), chosen after login on the new-chat screen.
- AST-aware chunking, line-number citations, code eval set, security hardening.

**Out of scope (later / optional, see Stage 14):** GitHub URL import, GitHub-as-MCP-server ingestion, private repos/OAuth, a code-specific embedding model, call-graph / cross-file symbol tracing, running code.

**Honest limits to keep in the README:** RAG over the top-5 chunks answers *local* questions (what does this function do, where is X) well and *global* questions (list every endpoint, whole-repo architecture) poorly. A project-map chunk (Stage 10) only partly helps.

---

## 2. Architecture

### 2.1 Target flow (new parts marked ★)

```
 SOURCES                      INGESTION (Celery worker)                 SEARCH / ANSWER (API)
 ───────                      ─────────────────────────                 ─────────────────────
 single/multi file ─┐
 zip upload ────────┼─► POST /documents ─► Postgres blob ─► task ─►  ★ resolve code mime
 folder (zipped in  │   (mode checked ★)                              ★ CodeLoader / ZipLoader
 browser ★) ────────┘                                                 ★ SKIP cleaner for code
                                                                      ★ CodeChunker (AST, headers)
                                                                      ★ project-map chunk
                                                                      embed (dense + BM25) ─► Qdrant
                                                                      (BM25 ★ identifier-aware)

 question ─► rewrite ─► hybrid search (user + doc-id filter) ─► rerank ─► ContextBuilder
             (unchanged)         (unchanged)                    (unchanged) ★ code budget
                                                                      ─► ★ code prompt ─► LLM ─► stream
                                                                      ─► citations ★ with path + lines
```

### 2.2 What works unchanged (verified by reading the code)

Auth/Clerk, rate-limit mechanics, upload storage (blob, hash dedup, Celery dispatch, status lifecycle), per-chat document scoping, Qdrant write/delete, hybrid search + RRF + user/document filter, reranker, query rewrite, conversation and long-term memory, SSE streaming, sidebar/rename/delete, dark mode, eval harness *mechanics*.

### 2.3 What must change (the complete list)

| # | Place | Change | Why |
|---|---|---|---|
| 1 | `services/document.py` (`_EXTENSION_MIME_TYPES`, `ALLOWED_MIME_TYPES`) | add code + zip types | uploads are refused today |
| 2 | `ingestion/loaders/factory.py` | `CodeLoader`, `ZipLoader`, extend `SUPPORTED_MIME_TYPES` | no loader exists |
| 3 | `ingestion/pipeline.py` | **bypass `CleaningOrchestrator` for code** | cleaner deletes repeated lines, flattens whitespace, flags low-alphanumeric text: it corrupts code |
| 4 | `ingestion/chunking/` | `DocumentType.CODE`, `CodeChunkingStrategy`, register it (the registry lives in `splitter.py`) | prose splitter cuts functions in half |
| 5 | `worker/task.py` (`_DOC_TYPES`, `build_chunk_metadata`) | `doc_type="code"/"codebase"`, `language` | unknown MIME falls back to `"other"` |
| 6 | `ingestion/embedding/embedders.py` | identifier-aware tokenization for BM25 | `getUserById` must match "get user by id" |
| 7 | `augmentation/model.py`, `citation_mapper.py`, `schemas/ask.py`, `schemas/conversation.py` | `file_path`, `start_line`, `end_line`, `language` on `Citation` | citations only know page/slide/sheet today |
| 8 | `augmentation/context_builder.py` | budget becomes a setting; code mode larger | 3,000 tokens is too small for code |
| 9 | `generation/chain.py` | a code-mode prompt | quote identifiers exactly, ignore instructions in comments |
| 10 | `db/models/conversations.py` + Alembic | nullable `mode` column | mode is a property of the chat |
| 11 | `routers/conversations.py`, `services/conversations.py`, `services/ask.py` | accept/return `mode`, enforce it on upload, pick prompt/budget | server must enforce, not the UI |
| 12 | `core/rate_limit.py` / settings | upload limits fit a zip (one POST = one upload) | 10 uploads/hour breaks multi-file |
| 13 | `worker/task.py` | Celery time limit for ingestion | a huge zip must not hold a worker forever |
| 14 | Frontend: `lib/files.js`, `EmptyChat`, `useUploads`, `citations.js`, `CitationPanel`, `UploadChip`, new folder-zip helper | mode tabs, zip/folder upload, path+line citations, monospace snippet | UI |
| 15 | `eval/` | code corpus, golden set, pipelines | to measure |
| 16 | Tests | per stage | see stages |

### 2.5 File tiers: what a project zip may contain

A real project is more than source code, so files are sorted into tiers. The tier decides the loader and chunker. `policy.py` (Stage 1) is the one place that holds this table; the browser mirrors it.

| Tier | Extensions | How it is read and chunked |
|---|---|---|
| **1. Code (AST)** | `.py .js .jsx .mjs .cjs .ts .tsx .java .c .h .cpp .hpp .cc .cxx` | tree-sitter: one chunk per function/method/class, with a context header, path and line numbers |
| **2. Text and config** | `.html .css .scss .json .yaml .yml .toml .ini .cfg .sql .sh .env.example .txt .md .rst .gitignore Dockerfile requirements.txt Makefile` | plain structure-aware splitting (headings for Markdown, blocks for the rest), with path and line numbers. `.md` is first-class: READMEs explain the project. |
| **3. Notebooks** | `.ipynb` | parse the JSON; keep **code and markdown cells** in order (one chunk per cell or small group, `cell N` as location); **drop all outputs** (see S19) |
| **4. Data files** | `.csv .tsv` | **never indexed in full.** Index the header, the row/column counts and the first N rows (about 20-50) as one "data sample" chunk. Large datasets would flood the index and the prompt (see S20). |
| **Skipped** | images, models and binaries (`.pkl .h5 .pt .onnx .zip`), `package-lock.json`, `yarn.lock`, `*.min.js`, `*.map`, build/vendor folders, `.env`, keys | counted and reported to the user, never indexed |

How this covers the project types you named:
- **MERN:** `.js .jsx` (AST), `package.json`, route and model files, `.env.example`, `.md`, `.css`, `.html`.
- **Flask/Python:** `.py` (AST), Jinja templates in `.html`, `requirements.txt`, `.yaml`, `.md`.
- **AI/ML:** `.py` (AST), `.ipynb` notebooks, `.md`, and `.csv` as a small sample only.

What this does **not** do: `.pdf`, `.docx` and other documents inside a zip are skipped in v1 (upload them to a Docs chat instead). Querying a whole dataset ("average of column X") is not something RAG can answer; the data sample only lets the model describe the file's shape.

### 2.4 Architecture decisions (the "why", for interviews)

| Decision | Choice | Why / alternative rejected |
|---|---|---|
| Ingestion architecture | **Indexed RAG** (ingest once, retrieve per question) | Agentic "GitHub MCP, fetch files live" is non-deterministic, depends on a small local model calling tools reliably, hits API rate limits and is hard to evaluate. |
| Source format | **Zip as the one codebase format**; folder is zipped in the browser | One safe ingestion path; one upload = one `documents` row = one chip; dedup/delete/scoping keep working. |
| Zip representation | One `documents` row, many source files inside (each chunk carries `file_path`) | Avoids 300 document rows, 300 chips and the 10 uploads/hour limit. |
| Mode | Stored on the **conversation**, chosen after login | Retrieval budget, prompt and accepted files are configured once; no guessing per message; no mixed PDF+code chats. |
| Chunking | AST (tree-sitter), one chunk per function/method, with a context header | Prose splitters cut mid-function. Start with LangChain language splitters, then upgrade only if the eval shows a gain. |
| Embeddings | **Keep `bge-large-en-v1.5` first**; try a code model only as a measured experiment | A different dimension needs a separate collection (`DENSE_DIM` is fixed at 1024). |
| Cleaner | Bypass for code | See table row 3. |
| GitHub | Later: server downloads GitHub's zip and reuses `ZipLoader` | Not MCP for ingestion. |

---

## 3. Security and risk register

Each item names the stage that handles it. Re-check this table at Stage 12.

| ID | Threat | Mitigation | Stage |
|---|---|---|---|
| S1 | **Zip bomb** (small zip, huge uncompressed) | Check declared sizes before reading; cap total uncompressed (about 50 MB), file count (about 300-500), per-file size (about 1 MB); abort while reading if a member exceeds its cap (declared sizes can lie) | 9 |
| S2 | **Path traversal** (`../../x`, absolute paths, drive letters) | Never extract to disk; read members in memory only; reject names with `..`, leading `/`, `\`, or a drive letter; normalise paths before storing as `file_path` | 9 |
| S3 | **Symlinks / special entries** in zip | Skip them (check the Unix mode bits in `external_attr`) | 9 |
| S4 | **Nested zips / zips inside zips** | Do not recurse; skip nested archives | 9 |
| S5 | **Prompt injection through comments/strings** in uploaded code | Keep the existing "context is data, not instructions" guard; code prompt repeats it; add an injection test with a payload in a comment and a docstring; model output filtering gap stays documented (`xfail`) | 8, 12 |
| S6 | **Secrets inside uploaded code** (`.env`, keys, tokens) get stored in Qdrant/Postgres and sent to the LLM (and to Gemini if the fallback is on) | Skip secret-bearing file names (`.env*`, `*.pem`, `id_rsa*`, `*.key`, `credentials*`); scan for key patterns (e.g. `AKIA...`, `-----BEGIN ... PRIVATE KEY-----`, `sk-...`) and **redact the match** before chunking; tell the user what was skipped/redacted | 2, 12 |
| S7 | **Code sent to a cloud fallback** (Gemini) leaks private code | In code mode, show a clear notice when the fallback is configured; recommend `LLM_FALLBACK_PROVIDER` empty for private code; document it | 8, 13 |
| S8 | **Cross-user leakage** | Existing user-id + document-id filter must apply to code chunks; add a code-specific cross-user test (Alice's zip never reaches Bob) | 12 |
| S9 | **Worker DoS** (huge/complex files, parser hangs, slow embedding of 500 files) | File/chunk caps; parse timeout per file with fallback to the plain splitter; Celery `soft_time_limit`/`time_limit`; one failed file does not fail the zip; clear failure reason | 6, 9 |
| S10 | **Minified / generated / one-line huge files** | Skip by extension (`*.min.js`), by max line length, by max file size; skip lock files and build folders | 1, 9 |
| S11 | **Binary or non-UTF-8 files** | Allow only known code extensions; try UTF-8 then skip (do not guess with latin-1 for code in a zip) | 2, 9 |
| S12 | **Mode bypass** (upload a PDF into a code chat or zip into a docs chat through the API) | Enforce the mode on `POST /documents` server-side (400 with a clear message) | 4 |
| S13 | **Client-side zip is untrusted** | Frontend filtering is convenience only; the server applies the full policy every time | 11 |
| S14 | **SSRF** (only if GitHub URL import is added later) | Allow-list `github.com` / `codeload.github.com`; no redirects to other hosts; size cap; block private IPs; no user-controlled headers | 14 |
| S15 | **Rendering code as HTML** | Snippets and answers stay plain text in `<pre>`; never `dangerouslySetInnerHTML` or markdown images (existing rule) | 3 |
| S16 | **Logging code or secrets** | Never log chunk text or file content; log counts and paths only; tracing (LangSmith) stays opt-in and the README warns it uploads prompts | 12 |
| S17 | **Storage growth / quota abuse** | Per-user cap on total code documents or bytes; existing rate limits apply | 9, 12 |
| S18 | **ReDoS in secret-scan regexes** | Use simple, anchored patterns; test with long adversarial lines; cap line length before scanning | 12 |
| S19 | **Notebook outputs** (`.ipynb` holds base64 images, huge outputs, and sometimes secrets or personal data printed by cells) | Parse the JSON safely (size cap first, `json` only); keep only `source` of code and markdown cells; drop every `outputs` field; reject malformed notebooks without failing the zip | 9 |
| S20 | **Data files** (`.csv`) flood the index, blow the prompt budget, and may contain personal data | Never index in full: header plus the first N rows only, with a hard byte cap; mention in the UI that only a sample is read; apply secret/PII-style redaction on the sample | 9, 12 |
| S21 | **Huge or generated JSON** (lock files, bundles, data dumps) | Skip known lock files; cap `.json` size (about 200 KB) and skip over the cap; never parse untrusted JSON recursively without a depth/size limit | 1, 9 |

### Architecture issues to watch (known traps in this codebase)

- **A1. Cleaner corrupts code** (see 2.3 row 3). Test: indentation and repeated `}`/`return` lines survive ingestion byte-for-byte.
- **A2. Context window.** `llm.py` sets `num_ctx=8192`. The prompt also carries history (~800 tokens), summary, memory (up to 500) and the answer. A code budget above about 4,500-5,000 tokens risks silent truncation. Choose the budget by measurement, and never exceed what fits.
- **A3. Qdrant payload indexes.** Add `language` only if filters need it; do not add indexes casually (re-index cost).
- **A4. Chunk IDs** are `uuid5(document_id, chunk_index)`: stable, but a zip's `chunk_index` must be unique across the whole zip (assign after all files are chunked, as `ChunkingOrchestrator` already does with `_attach_metadata`).
- **A5. `source` metadata.** Embedding falls back to `source` only without a `document_id`; for zips keep `source_name` = the zip filename and add `file_path` separately. Do not overload `source_name`.
- **A6. Dedup is by whole-file hash**, so the same project zipped twice differently is two documents. Acceptable; note it.
- **A7. Reranker** (`bge-reranker-base`) is trained on prose. It may hurt code. The eval decides; keep a "no rerank" comparison column.
- **A8. Dense model** is English-prose trained. Identifier-heavy queries lean on BM25, so Stage 7 matters.
- **A9. Old persisted citations** lack the new fields. All new fields are optional; the frontend must tolerate missing ones.
- **A10. Mixed-mode history.** A chat has one mode; never let a chat's mode change after its first document or message.
- **A11. Docker image** needs any new native dependency (tree-sitter wheels) in `requirements.txt` and the `Dockerfile` (check both; keep `requirements.txt` UTF-8).

---

## 4. Stages

Every stage ends with **STOP**. Each lists: *Learn · Files · Do · Security · Tests · Done when*.

### Stage 0: Baseline and housekeeping 🟡
**Status:** branch `feature/codebase-chat` created and used (never `main`). The test-count baseline and the optional cleanups were not recorded separately; the code eval baseline is in section 6.
**Learn:** why you record a baseline *before* changing anything.
**Do:**
1. Create a branch (e.g. `feature/code-chat`).
2. Run the full backend and frontend tests; record counts. Fix nothing yet.
3. Save the current eval report as the **prose baseline** (`eval/results/latest.md` copy; do not re-run the one-hour eval unless asked).
4. Optional small cleanups, only if the owner approves each separately: the StrictMode bug in `ChatLayout` (set `conversation.current.id` only after load succeeds), a CI workflow, and the registry/`splitter.py` file naming.
**Tests:** existing suite only.
**Done when:** baseline numbers are written in this file under "Baseline log" (section 6).
**STOP.**

### Stage 1: One policy, one source of truth ✅
**Status:** done (2271154). Lives in `backend/app/ingestion/codebase/policy.py`, 114 tests in `tests/test_codebase_policy.py`.
**Learn:** an *allow-list* beats a deny-list; keeping rules in one module stops the frontend and backend drifting apart.
**Files:** new `backend/app/ingestion/code/policy.py` (+ `backend/tests/test_code_policy.py`).
**Do:** define, with no behaviour change yet:
- The **file tier table from section 2.5** as data: `TIER1_CODE` (extension → language), `TIER2_TEXT`, `TIER3_NOTEBOOK`, `TIER4_DATA`, plus per-tier size caps (e.g. text 200 KB, data sample bytes, code 1 MB). Name-based entries too (`Dockerfile`, `Makefile`, `requirements.txt`).
- `IGNORED_DIRS` (`node_modules .git venv .venv env dist build target out __pycache__ .idea .vscode vendor`), `IGNORED_FILES` (lock files, `*.min.js`, `*.map`).
- `SECRET_FILE_PATTERNS` (S6), size caps (`MAX_FILE_BYTES`, `MAX_ZIP_UNCOMPRESSED`, `MAX_FILES`, `MAX_LINE_LENGTH`).
- `is_ignored_path(path)`, `language_for(path)`, `is_safe_member_name(name)` (S2).
**Security:** S2, S6, S10, S11 start here.
**Tests (unit):** traversal names, absolute paths, Windows paths, ignored dirs, extension map, minified names.
**Done when:** policy tests pass; no other file changed.
**STOP.**

### Stage 2: Ingest a single code file end-to-end (docs unchanged) ✅
**Status:** done (7c3a643), single-file part. Loader is `loaders/code_loader.py`, stored MIME `text/x-code`. Zip ingestion stays in Stage 9.
**Learn:** how one file travels `upload → blob → Celery → loader → chunk → Qdrant`, and why the cleaner must be bypassed.
**Files:** `services/document.py`, `loaders/factory.py`, new `loaders/code.py`, `ingestion/pipeline.py`, `chunking/model.py` + registry (`splitter.py`), `worker/task.py`, tests.
**Do:**
1. Map code extensions to MIME types (extension first; browsers send odd types); allow them.
2. `CodeLoader`: decode UTF-8 (skip non-UTF-8, S11), set `language`, `file_path` (= filename for a single file), keep text byte-for-byte.
3. `pipeline.py`: for code MIME types skip the cleaner (keep an empty-file check) and skip OCR.
4. `DocumentType.CODE` + a first, simple `CodeChunkingStrategy` using LangChain `RecursiveCharacterTextSplitter.from_language(...)`. Add `language`, `file_path` to metadata; chunk text still plain.
5. `worker/task.py`: `doc_type="code"`, `language` in `build_chunk_metadata`.
6. Secret handling v1: refuse files whose name matches `SECRET_FILE_PATTERNS` with a friendly reason (S6).
**Security:** S6 (file names), S11.
**Tests:** unit (loader, strategy); **A1 test** (indentation and repeated lines survive through the real pipeline); integration (upload a `.py` through the API and see `ready`, chunks in Qdrant with `language`).
**Done when:** a Python file uploads, reaches `ready`, and a plain-text question retrieves its chunks; docs tests all still pass.
**STOP.**

### Stage 3: Citations with path and lines ✅
**Status:** done (f57e32d).
**Learn:** how a citation travels from chunk metadata → `Citation` → API JSON → React.
**Files:** `augmentation/model.py`, `citation_mapper.py`, `schemas/ask.py`, `schemas/conversation.py`, `chunking` (store `start_line`/`end_line`), frontend `citations.js`, `CitationPanel`, `UploadChip` label, tests.
**Do:** add optional `file_path`, `start_line`, `end_line`, `language` end to end; the panel shows `path · lines a-b` and renders the snippet in a monospace `<pre>` (plain text). Make the chunker compute line numbers.
**Security:** S15 (plain text only); A9 (old citations without the fields must still render).
**Tests:** backend unit + API (fields present, others absent for docs); frontend Vitest for `toCitation` and the panel.
**Done when:** a code answer shows `file.py · lines 40-72` and code in monospace; PDF citations look unchanged.
**STOP.**

### Stage 4: Mode per conversation ✅
**Status:** done (bdd9773). Decided with the owner: `mode` is NOT NULL, default `docs` (not nullable as written below); a code chat accepts source files plus `.md/.txt/.markdown`; enforced twice on the server.
**Learn:** why the server enforces rules the UI also shows; what a safe Alembic migration looks like.
**Files:** `db/models/conversations.py`, new migration, `routers/conversations.py`, `services/conversations.py`, `services/document.py` (enforcement), `services/ask.py` (read mode), frontend `EmptyChat`, `ChatLayout`, `lib/files.js`, tests.
**Do:**
1. Nullable `mode` (`docs` | `code`; null = `docs` for old rows). Optional `mode` on `POST /conversations`; returned in list/detail.
2. Enforce on upload (S12): a `docs` chat refuses code/zip, a `code` chat refuses documents; mode cannot change after the first document or message (A10).
3. Frontend: two cards on the new-chat screen ("Documents", "Codebase"); the accepted file types follow the mode.
**Security:** S12.
**Tests:** migration up/down on the test DB; API tests for each refusal; frontend test for the mode cards.
**Done when:** both modes work independently and a wrong-type upload is refused by the API, not just the UI.
**STOP.**

### Stage 5: Code eval set and baseline numbers ✅
**Status:** done. Built as a NEW folder `backend/eval_code/` (not `eval/`), so the docs evaluation and its tests are untouched: frozen 24-file corpus of this project, 25 questions (dev 17 / test 8, sealed), own metrics (incl. citation line hit), RAGAS with the local Qwen3 8B judge, own Qdrant collection `knowledgeos_eval_code`. Baseline numbers are in section 6.
**Learn:** why you build the test *before* the improvement; why you keep a dev and a test split.
**Files:** `backend/eval/` (new code corpus, `code_golden_set.jsonl`, a pipeline config), `eval/README.md`.
**Do:**
1. Choose a small real repo (the owner's own backend, or a small open-source one) as the corpus.
2. Write about 30 questions: local (what does X do, where is Y), cross-function, and **a few global ones on purpose** (they should fail; that is a finding).
3. Split dev (about 20) and test (about 10); tune only on dev; report test once at the end.
4. Run the **baseline** with the Stage 2 chunker. Record Hit@5, MRR, answer correct, cites expected file/lines.
**Tests:** harness tests for the new metrics.
**Done when:** a baseline table exists in section 6.
**STOP.**

### Stage 6: AST chunking (tree-sitter) ✅ (Tier 1 code; Tier 2/3 chunkers wait for Stage 9)
**Status:** done, measured in section 6. Packages (bundled grammars, no runtime download): `tree-sitter` + six grammar wheels, pinned in `requirements.txt`. Falls back to the Stage 2 splitter on syntax errors, unsupported language, files over 1,000,000 bytes or any exception. 42 tests in `tests/test_codebase_ast_chunking.py`.
**Learn:** what an AST is; why chunk boundaries matter for retrieval; how a context header helps embeddings.
**Files:** `chunking/` (new AST strategy), `requirements.txt`, `Dockerfile` check (A11), tests, eval run.
**Do:** cover every Tier 1 language (Python, JS/JSX, TS/TSX, Java, C, C++); Tier 2 and 3 files use their simpler chunkers (Markdown by heading, notebooks by cell, config by block). One chunk per function/method; split oversized classes into methods with the class signature and imports repeated; a header such as `# File: auth/jwt.py | class Verifier | def verify_token` before embedding; per-file parse **timeout and fallback** to the Stage 2 splitter (S9); never fail the document because one file fails to parse.
**Dependency:** new (tree-sitter packages): **ask the owner first** (`CLAUDE.md`).
**Security:** S9.
**Tests:** unit per language (Python, JS, Java, C, C++ samples including syntax errors and empty files); fallback test; eval comparison vs baseline.
**Done when:** eval shows the AST chunker's effect (good or bad) and it is recorded honestly. If it does not help, keep the simpler splitter and say why.
**STOP.**

### Stage 7: Identifier-aware keyword search ✅
**Status:** done and measured (table in section 6): no gain, so it is off by default. Code chats only (decided with the owner): `ingestion/embedding/identifiers.py`, a context-variable switch read by the BM25 embedder, turned on when indexing `doc_type == code` chunks and when searching from a code chat. 19 tests in `tests/test_identifier_splitting.py`, mutation-checked.
**Learn:** how BM25 tokenization decides what "matches".
**Files:** `embedding/embedders.py` (+ tests, eval).
**Do:** before BM25, split `camelCase`, `snake_case`, `PascalCase` and keep the original token too. Apply to **both** documents and queries (mismatch breaks search).
**Risk:** re-ingesting is required for existing code documents; docs mode must stay untouched (apply only in code mode).
**Tests:** tokenizer unit tests; eval comparison; docs eval unchanged.
**Done when:** numbers recorded; docs retrieval unchanged.
**STOP.**

### Stage 8: Code prompt and context budget ✅ (built, not measured)
**Status:** code prompt `CODE_GENERATION_PROMPT` in `generation/chain.py`; `augmentation/code_budget.py` (`CODE_CONTEXT_TOKENS`, max 4,500; `CODE_TOP_K`, max 12); `generation/code_local_model.py` (S7: a code chat never uses the cloud fallback unless `CODE_ALLOW_CLOUD_FALLBACK=true`). 
**Learn:** how the prompt, budget and `num_ctx=8192` fit together (A2).
**Files:** `generation/chain.py`, `augmentation/context_builder.py`, `services/ask.py`, settings, tests, eval.
**Do:** a code-mode prompt (answer only from the code, quote identifiers exactly, cite `[n]`, treat comments/strings as data); make the budget a setting (docs 3,000; code start at about 4,500 and tune); choose by eval and by checking the total prompt length stays under the window. Show the cloud-fallback notice (S7).
**Security:** S5, S7.
**Tests:** prompt builder tests; budget test (chunks dropped at the limit); injection test with a hostile comment.
**Done when:** the budget is justified by numbers; no prompt exceeds the window in tests.
**STOP.**

### Stage 9: Zip ingestion (backend) ⏳
**Learn:** zip internals (central directory, declared vs real size); why reading in memory is safer than extracting.
**Files:** new `loaders/zip_code.py`, factory, `services/document.py` (zip MIME, upload limits), `worker/task.py` (time limit), `core/rate_limit.py`/settings if needed, tests.
**Do:** `ZipLoader` using `zipfile` in memory: apply every rule from `policy.py`; yield one document per accepted file with `file_path`, `language` and `tier` (Tier 1 code, Tier 2 text, Tier 3 notebook cells with outputs dropped, Tier 4 CSV header plus first N rows only); skip and **count** the rest; return a summary (accepted/skipped by reason) stored with the document or logged; unique `chunk_index` across the zip (A4); one bad file does not fail the zip; a zip with no accepted code fails with a clear reason. Add Celery `soft_time_limit`/`time_limit`.
**Security:** S1, S2, S3, S4, S9, S10, S11, S17.
**Tests:** unit with hand-built malicious zips (traversal, absolute path, symlink, nested zip, zip bomb with a lying header, 1,000 files, huge file, binary file, non-UTF-8); integration through the real worker (a small real project zip reaches `ready`).
**Done when:** every malicious fixture is refused or skipped safely and a normal project zip is searchable.
**STOP.**

### Stage 10: Project-map chunk ⏳
**Learn:** why retrieval struggles with global questions and how an index chunk helps.
**Files:** the zip/code loader or chunker, tests, eval.
**Do:** generate one extra chunk per project listing paths and top-level classes/functions (from the AST, no LLM call), marked `chunk_kind="project_map"`; cap its size (split if large).
**Tests:** unit; eval's global questions before/after (expect partial improvement; report honestly).
**Done when:** results recorded.
**STOP.**

### Stage 11: Frontend: zip upload and "Choose folder" ⏳
**Learn:** how a browser reads a folder (`webkitdirectory`, drag-and-drop entries) and zips it client-side.
**Files:** `lib/files.js`, a new `lib/zipFolder.js`, `useUploads`, `EmptyChat`/composer UI, tests, `package.json` (a small zip library such as `fflate`: **ask first**).
**Do:** in a code chat show *Upload zip* and *Choose folder* (desktop only); for a folder, apply the same allow-list/ignore rules as `policy.py` (kept in sync by a shared fixture test), zip in the browser, show "Packed N files (X MB). Skipped M (node_modules, images...)", then upload through the existing queue; help text for compressing a folder on macOS/Windows.
**Security:** S13 (the server re-validates everything).
**Tests:** Vitest for the filter and summary (mocked file entries); manual browser check.
**Done when:** a real folder is zipped, uploaded, ingested and answered about; a 500 MB `node_modules`-heavy folder produces a small zip.
**STOP.**

### Stage 12: Security hardening pass ⏳
**Learn:** how to review your own feature like an attacker.
**Do:**
1. Secret scanning and **redaction** before chunking (S6, S18) with an upload warning; file-name skips already exist.
2. Re-run the register (section 3) line by line; for each ID, point to a test.
3. Cross-user test for code chunks (S8); a prompt-injection test in comments and docstrings (S5); no content in logs (S16); a per-user code quota (S17).
4. Update the documented `xfail` gaps if any changed.
**Tests:** one named test per register ID where testable; mutation-check two of them (break the guard and see the test fail).
**Done when:** the register has a test or a written reason for every row.
**STOP.**

### Stage 13: Docs, evaluation report, demo ⏳
**Do:** update `README.md` (new mode, flow diagram, **code eval table with honest numbers and the global-question failures**, security notes including S6/S7), `CLAUDE.md` current-state entries, `docs/architecture.png` if the flow changed, and the blog. Record a short demo. Add CI if it was not done at Stage 0. Run the full suites and the code eval once more (report on the **test split**).
**Done when:** the README numbers come from real runs and a reader can reproduce them.
**STOP.**


---

## 5. Definition of done for the whole feature

- Docs mode behaves exactly as before; all existing tests still pass.
- Code mode: single file and zip both work; folder is zipped in the browser.
- Every security register item has a test or a documented decision.
- The code eval table (dev and test split, baseline vs each change) is in the README, including where it fails.
- The owner can explain, without notes, each stage's concept (the "Learn" lines).

## 6. Logs (fill in as you go)

**Baseline log (Stage 0/5):** backend tests: 889 passed (after Stage 4), 993 after Stage 8 (974 after Stage 6; one docs-eval test, test_corpus_is_deterministic, failed once in a full run and passed 7 times alone: flaky, not touched) · frontend tests: 191 · prose eval: see `eval/results/latest.md` (untouched) · code eval baseline (dev split, 17 questions, Stage 2 splitter, 85 chunks): dense Hit@5 0.71 / MRR 0.60, hybrid 0.86 / 0.88, hybrid+rerank 0.86 / 0.77; answers correct 0.71 / 0.79 / 0.79.

**Code eval results (one table; dev split, 17 questions).** Per-run reports and flipped questions: `backend/eval_code/results/` (`comparison.md`, `comparison_identifiers.md`). Columns are cumulative: each one changes only the thing named.

| Metric (dev split, 17 questions) | Splitter (baseline) | AST | AST + header | AST + identifiers |
|---|---|---|---|---|
| Hit@5, dense | 0.71 | 0.86 | 0.79 | 0.86 |
| Hit@5, hybrid | 0.86 | 0.93 | 0.86 | 0.93 |
| Hit@5, hybrid+rerank | 0.86 | 0.79 | 0.79 | 0.79 |
| MRR, dense | 0.60 | 0.77 | 0.65 | 0.77 |
| MRR, hybrid | 0.88 | 0.82 | 0.73 | 0.79 |
| MRR, hybrid+rerank | 0.77 | 0.80 | 0.83 | 0.80 |
| Answers correct, dense | 0.71 | 0.79 | 0.86 | 0.79 |
| Answers correct, hybrid | 0.79 | 0.86 | 0.93 | 0.86 |
| Answers correct, hybrid+rerank | 0.79 | 0.86 | 1.00 | 0.86 |
| False refusals, hybrid+rerank | 0.00 | 0.00 | 0.00 | 0.00 |
| Refuses out-of-scope, hybrid | 0.67 | 1.00 | 1.00 | 0.67 |
| Refuses out-of-scope, hybrid+rerank | 1.00 | 1.00 | 1.00 | 1.00 |
| Cites right file AND lines, hybrid+rerank | 1.00 | 1.00 | 0.86 | 1.00 |
| Citation line precision, hybrid+rerank | 0.96 | 0.90 | 0.82 | 0.90 |
| RAGAS faithfulness, hybrid+rerank | 0.89 | 0.94 | 0.93 | 0.94 |
| RAGAS answer relevancy, hybrid+rerank | 0.90 | 0.91 | 0.89 | 0.91 |
| RAGAS context precision, hybrid+rerank | 0.82 | 0.89 | 0.94 | 0.89 |
| RAGAS context recall, hybrid+rerank | 0.93 | 1.00 | 1.00 | 1.00 |
| Tokens per question, hybrid+rerank | 2191 | 1589 | 1609 | 1613 |
| Generation p50 (s), hybrid+rerank | 9.8 | 6.2 | 6.3 | 6.0 |

Reading it: AST chunking is the one clear win (dense Hit@5 0.71 to 0.86, answers correct up in all three configurations, about 600 fewer tokens per question). Under hybrid + rerank Hit@5 is one question lower (c13, a global question expected to fail). The `# File: path | symbols` header lifts answers correct but costs line-accurate citations (1.00 to 0.86) and hybrid MRR, and its gain comes from three flipped questions, so it stays off. Splitting identifiers (`take_token` into `take token` for keyword search) changed nothing measurable (Hit@5 identical everywhere; the 0.67 in one cell is a single out-of-scope question), so it stays off by default. 17 questions are few: **one question is about 6 points**, so gaps of one or two questions are noise, and the RAGAS judge is a small local model, so compare columns rather than trusting absolute values. Stage 8 (the code prompt, the context budget and the no-cloud-fallback rule) is built but **not measured**: its eval was skipped on purpose. The sealed test split (8 questions) has not been run.

**Decision (2026-11-24):** `CODE_CHUNKER=ast` stays the default; `CODE_CHUNK_HEADER=false` stays off (it costs line-citation accuracy and retrieval ranking for an unproven gain). Revisit the header with a larger question set. The sealed test split has not been run (Stage 13 only).

**Decision (2026-11-26):** `CODE_SPLIT_IDENTIFIERS=false` (Stage 7 showed no measurable gain; the code stays, code chats only). Stage 8 eval skipped by the owner's choice; `CODE_CONTEXT_TOKENS=3000` and `CODE_TOP_K=5` keep the old behaviour until someone measures a change, `CODE_ALLOW_CLOUD_FALLBACK=false` (S7).

**Decision log:** (date · decision · reason · measured result)

**Decided:** dependency for Stage 6 = tree-sitter core plus six bundled grammars (no runtime download). Eval for code lives in `backend/eval_code/`, separate from `eval/`. `.jsx .mjs .cjs .ts .tsx` are Tier 1 code; `.md`, `.csv` (sample only), `.ipynb` (outputs dropped), config and web files are supported as in section 2.5.

**Open questions for the owner:** Per-user code quota size? Keep the cloud fallback on in code mode? How many CSV sample rows (default 30)? Should a docs-type file (PDF, DOCX) inside a zip be skipped (default) or ingested?
