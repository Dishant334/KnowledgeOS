# Frozen code corpus for the codebase evaluation

A **copy** of 24 files of KnowledgeOS taken at commit `bdd9773` (Python backend + JavaScript frontend).

Do not edit these files and do not refresh them from the live repo: the golden set (`../code_golden_set.jsonl`)
points at exact passages and line numbers in THEM. If the snapshot ever has to change, re-verify every question
(`pytest tests/test_eval_code.py`) and re-run the baseline, because old numbers no longer compare.

Paths below are the paths used as `source_name` / `file_path` in the evaluation.

| file | lines | sha256 (first 16) |
|---|---|---|
| `backend/app/core/rate_limit.py` | 222 | `906e603aa81ecfe1` |
| `backend/app/core/cors.py` | 40 | `1505d03746c69772` |
| `backend/app/services/document.py` | 297 | `0722fb2c155b523e` |
| `backend/app/services/conversations.py` | 246 | `eb872b4a652623e2` |
| `backend/app/services/small_talk.py` | 24 | `c141b4f213aa7561` |
| `backend/app/services/introductions.py` | 214 | `526b08c0c467bfec` |
| `backend/app/schemas/document.py` | 49 | `7d7994114c9c2ec0` |
| `backend/app/augmentation/citation_mapper.py` | 71 | `84c9a4c3e996e013` |
| `backend/app/augmentation/context_builder.py` | 49 | `197db48fa615d2e2` |
| `backend/app/retrieval/orchestrator.py` | 132 | `d9734bc94195ba34` |
| `backend/app/retrieval/filters.py` | 44 | `f672575fe058df01` |
| `backend/app/retrieval/multi_query.py` | 57 | `56338f7b478e3345` |
| `backend/app/memory/store.py` | 176 | `d382dc2da28819fa` |
| `backend/app/generation/orchestrator.py` | 297 | `2da9d1db81a8b939` |
| `backend/app/ingestion/hashing.py` | 5 | `2715d661bbf2fed9` |
| `backend/app/ingestion/chunking/strategies.py` | 280 | `1e2cacb389aa8a8d` |
| `backend/app/ingestion/codebase/policy.py` | 196 | `74f64245139b2457` |
| `backend/app/ingestion/loaders/code_loader.py` | 56 | `1e9292ffcc8b1ee2` |
| `frontend/src/api/askStream.js` | 81 | `07b5d9ecd7efc9f6` |
| `frontend/src/api/errors.js` | 59 | `8fa349c45bf7b9eb` |
| `frontend/src/features/chat/citations.js` | 52 | `353ce48472f47e2d` |
| `frontend/src/features/documents/useUploads.js` | 168 | `4cec532adc9a3bd7` |
| `frontend/src/lib/files.js` | 67 | `bf9bc32b65d0f7b8` |
| `frontend/src/lib/ripple.js` | 20 | `bedf1ce05a2ca1bf` |
