# eval_code/suite.py
"""
The codebase evaluation's data: a FROZEN copy of source files and the questions about them.

  corpus/         24 files of this project (Python backend + JavaScript frontend), copied once. Frozen on purpose:
                  the golden set points at exact passages and line numbers in THESE files, so they must not move when
                  the live code changes. See corpus/MANIFEST.md (it records a hash per file; a test checks it).
  golden_set.jsonl  25 questions, each with the verbatim passage that answers it and a `split`:
                  "dev" (17) is what we look at and tune on; "test" (8) is kept sealed and reported once at the end,
                  so later improvements cannot quietly overfit the questions we have been staring at.

This package is separate from `eval/` (the documents evaluation) on purpose: nothing here imports or changes it.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"
GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.jsonl"
MANIFEST_NAME = "MANIFEST.md"          # documentation about the folder, not part of the corpus
SPLITS = ("dev", "test")


@dataclass
class SourceFile:
    filename: str      # path relative to the corpus folder, e.g. "backend/app/core/rate_limit.py"
    kind: str          # "code"
    mime: str
    data: bytes
    text: str


def corpus_paths() -> list[Path]:
    """Every file of the frozen corpus, in a fixed order (the manifest is not one of them)."""
    return sorted(p for p in CORPUS_DIR.rglob("*") if p.is_file() and p.name != MANIFEST_NAME and "__pycache__" not in p.parts)


def build_corpus() -> list[SourceFile]:
    """
    The corpus as files for eval_code/ingest.py. Each file is checked with the project's own file policy: it must be a
    Tier 1 source file and must not look like a secret. The name is the path relative to the corpus folder and becomes
    the chunks' `source_name` and `file_path`.
    """
    from app.ingestion.codebase.policy import TIER_CODE, classify
    from app.ingestion.loaders.code_loader import CODE_MIME_TYPE

    files = []
    for path in corpus_paths():
        name = path.relative_to(CORPUS_DIR).as_posix()
        verdict = classify(name)
        if not verdict.accepted or verdict.tier != TIER_CODE:
            raise ValueError(f"{name} is not an acceptable corpus file: {verdict}")
        data = path.read_bytes()
        files.append(SourceFile(filename=name, kind="code", mime=CODE_MIME_TYPE, data=data, text=data.decode("utf-8")))
    return files


@lru_cache(maxsize=None)
def corpus_text(name: str) -> str:
    return (CORPUS_DIR / name).read_text(encoding="utf-8")


def _passage_pattern(passage: str) -> re.Pattern:
    """The passage as a pattern: any run of whitespace matches any other (a passage may span two lines)."""
    return re.compile(r"\s+".join(re.escape(word) for word in passage.split()), re.IGNORECASE)


def find_passage(text: str, passage: str) -> list[tuple[int, int]]:
    """Character spans where the passage occurs (ignoring case and differences in whitespace)."""
    return [m.span() for m in _passage_pattern(passage).finditer(text)]


def passage_lines(text: str, passage: str) -> tuple[int, int] | None:
    """
    (first line, last line), 1-based, of the passage, or None if it is not found EXACTLY ONCE.
    Exactly once, so a golden question can never point at an ambiguous spot.
    """
    spans = find_passage(text, passage)
    if len(spans) != 1:
        return None
    start, end = spans[0]
    return text.count("\n", 0, start) + 1, text.count("\n", 0, end - 1) + 1


def load_golden_set(split: str | None = None, path: Path = GOLDEN_SET_PATH) -> list[dict]:
    """
    The questions (all, or one split). Every expected passage also gets `lines` = [first, last], worked out from the
    frozen file, so the metrics can check whether a citation points at the right lines. The numbers are never typed by
    hand, so they cannot drift from the code.
    """
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in rows:
        for expected in row["expected"]:
            lines = passage_lines(corpus_text(expected["doc"]), expected["passage"])
            expected["lines"] = list(lines) if lines else None
    return [r for r in rows if split in (None, "all") or r["split"] == split]
