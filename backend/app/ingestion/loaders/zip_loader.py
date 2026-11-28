# CODEBASE-FEATURE (Stage 9): loader for a PROJECT ZIP.
#
# The zip is opened IN MEMORY with the standard library and never extracted to disk, so a hostile member name can
# not write anywhere (S1/S2). Every member goes through the same rules as a single uploaded file (policy.py) plus
# the zip-specific ones (S3 bombs, S4 symlinks, nested archives, entry and size caps). One bad file is skipped and
# counted; it never fails the whole zip.
import io
import json
import stat
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from langchain_core.documents import Document

from app.ingestion.codebase.policy import (
    ARCHIVE_SUFFIXES,
    DATA_SAMPLE_MAX_BYTES,
    DATA_SAMPLE_ROWS,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_LINE_LENGTH,
    MAX_ZIP_ENTRIES,
    MAX_ZIP_UNCOMPRESSED,
    SKIP_DUPLICATE,
    SKIP_EMPTY,
    SKIP_ENCRYPTED,
    SKIP_MINIFIED,
    SKIP_NESTED_ARCHIVE,
    SKIP_NOT_UTF8,
    SKIP_SIZE_LIMIT,
    SKIP_SYMLINK,
    SKIP_TOO_LARGE,
    SKIP_TOO_MANY_FILES,
    SKIP_UNREADABLE,
    TIER_CODE,
    TIER_DATA,
    TIER_NOTEBOOK,
    TIER_TEXT,
    classify,
    is_safe_member_name,
    normalize_path,
)
from app.ingestion.loaders.base import BaseLoader

# Stored MIME type of a project zip. The upload service decides it from the extension (browsers label zips
# application/zip, application/x-zip-compressed, application/octet-stream...).
ZIP_MIME_TYPE = "application/zip"

# A member bigger than this that compresses more than this much is a bomb, whatever its size cap says (S3).
_BOMB_MIN_BYTES = 1_000_000
_BOMB_MAX_RATIO = 200

_TEXT_LANGUAGES = {
    ".md": "markdown", ".rst": "rst", ".txt": "text", ".json": "json", ".yaml": "yaml", ".yml": "yaml",
    ".toml": "toml", ".ini": "ini", ".cfg": "ini", ".html": "html", ".css": "css", ".scss": "scss",
    ".sql": "sql", ".sh": "shell",
}
_NAME_LANGUAGES = {"dockerfile": "dockerfile", "makefile": "makefile"}


@dataclass
class ZipSummary:
    """What was read and what was left out. Counts and reasons only: never file names or content (S16)."""

    accepted: int = 0
    total_bytes: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    by_tier: dict[str, int] = field(default_factory=dict)

    def describe(self) -> str:
        files = f"{self.accepted} file{'s' if self.accepted != 1 else ''} read"
        if not self.skipped:
            return f"zip: {files}, none skipped"
        reasons = ", ".join(f"{reason}: {count}" for reason, count in sorted(self.skipped.items()))
        return f"zip: {files}, {sum(self.skipped.values())} skipped ({reasons})"


class ZipLoader(BaseLoader):
    """One Document per accepted file, each with the path INSIDE the project as its `file_path`."""

    def load(self, data: bytes, filename: str, metadata: dict[str, Any] | None = None) -> list[Document]:
        return self.load_with_summary(data, filename, metadata)[0]

    def load_with_summary(
        self, data: bytes, filename: str, metadata: dict[str, Any] | None = None
    ) -> tuple[list[Document], ZipSummary]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except (zipfile.BadZipFile, ValueError, OSError) as exc:
            raise ValueError("Not a valid zip file") from exc

        with archive:
            members = archive.infolist()
            if len(members) > MAX_ZIP_ENTRIES:
                raise ValueError(f"Zip has too many entries ({len(members)})")
            return self._read(archive, members, metadata or {})

    # ------------------------------------------------------------------------------------------

    def _read(self, archive: zipfile.ZipFile, members: list[zipfile.ZipInfo], metadata: dict[str, Any]):
        summary = ZipSummary()
        skipped: Counter[str] = Counter()
        prefix = _common_top_folder([m.filename for m in members if not m.is_dir()])
        documents: list[Document] = []
        seen: set[str] = set()
        budget_left = MAX_ZIP_UNCOMPRESSED

        # sorted by path: the same zip always gives the same documents, in the same order
        entries = sorted((m for m in members if not m.is_dir()), key=lambda m: normalize_path(m.filename).lower())
        for index, member in enumerate(entries):
            path = _project_path(member.filename, prefix)

            if not is_safe_member_name(member.filename):
                skipped["unsafe_path"] += 1
                continue
            if stat.S_ISLNK(member.external_attr >> 16):                      # S4: a link could point anywhere
                skipped[SKIP_SYMLINK] += 1
                continue
            if member.flag_bits & 0x1:
                skipped[SKIP_ENCRYPTED] += 1
                continue
            if PurePosixPath(path.lower()).suffix in ARCHIVE_SUFFIXES:        # never open an archive inside an archive
                skipped[SKIP_NESTED_ARCHIVE] += 1
                continue

            verdict = classify(path)
            if not verdict.accepted:
                skipped[verdict.skip_reason] += 1
                continue
            if path in seen:
                skipped[SKIP_DUPLICATE] += 1
                continue
            if len(documents) >= MAX_FILES:
                skipped[SKIP_TOO_MANY_FILES] += 1
                continue

            cap = MAX_FILE_BYTES[verdict.tier]
            declared, packed = member.file_size, max(member.compress_size, 1)
            if declared > cap or (declared > _BOMB_MIN_BYTES and declared / packed > _BOMB_MAX_RATIO):
                skipped[SKIP_TOO_LARGE] += 1
                continue
            if declared > budget_left:
                # the whole zip may only unpack to MAX_ZIP_UNCOMPRESSED bytes: stop reading, count what is left
                skipped[SKIP_SIZE_LIMIT] += len(entries) - index
                break

            limit = min(cap, budget_left)
            content = _read_member(archive, member, limit)
            if content is None:
                skipped[SKIP_UNREADABLE] += 1
                continue
            if len(content) > limit:                                          # the header lied about its size
                if limit == cap:
                    skipped[SKIP_TOO_LARGE] += 1
                    continue
                skipped[SKIP_SIZE_LIMIT] += len(entries) - index
                break
            budget_left -= len(content)
            summary.total_bytes += len(content)

            document, reason = _to_document(content, path, verdict.tier, verdict.language, metadata)
            if document is None:
                skipped[reason] += 1
                continue
            seen.add(path)
            documents.append(document)
            summary.by_tier[verdict.tier] = summary.by_tier.get(verdict.tier, 0) + 1

        summary.accepted = len(documents)
        summary.skipped = dict(skipped)
        if not documents:
            detail = f" ({sum(skipped.values())} skipped)" if skipped else ""
            raise ValueError(f"No usable files in the zip{detail}")
        return documents, summary


def _common_top_folder(names: list[str]) -> str | None:
    """`repo-main` when EVERY file sits inside that one folder (a GitHub download), else None. Mac forks are ignored."""
    first_parts = set()
    for name in names:
        if not is_safe_member_name(name):
            continue
        parts = normalize_path(name).split("/")
        if parts[0].lower() == "__macosx":
            continue
        if len(parts) < 2:
            return None                     # a file at the root: the project has no wrapper folder
        first_parts.add(parts[0])
    return first_parts.pop() if len(first_parts) == 1 else None


def _project_path(name: str, prefix: str | None) -> str:
    path = normalize_path(name) if is_safe_member_name(name) else name
    if prefix and path.startswith(prefix + "/"):
        return path[len(prefix) + 1:]
    return path


def _read_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, limit: int) -> bytes | None:
    """The member's real bytes, never more than limit + 1 (so a lying header can not make us read a bomb)."""
    try:
        with archive.open(member) as handle:
            return handle.read(limit + 1)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, ValueError):
        return None


def _decode(content: bytes) -> str | None:
    try:
        return content.decode("utf-8-sig")        # strict: guessing an encoding silently produces garbage (S11)
    except UnicodeDecodeError:
        return None


def _too_wide(text: str) -> bool:
    return any(len(line) > MAX_LINE_LENGTH for line in text.splitlines())


def _to_document(content: bytes, path: str, tier: str, language: str | None, metadata: dict[str, Any]):
    """(Document, None) or (None, skip reason)."""
    text = _decode(content)
    if text is None:
        return None, SKIP_NOT_UTF8
    if not text.strip():
        return None, SKIP_EMPTY

    if tier in (TIER_CODE, TIER_TEXT) and _too_wide(text):
        return None, SKIP_MINIFIED

    if tier == TIER_NOTEBOOK:
        parsed = _notebook_text(text)
        if parsed is None:
            return None, SKIP_UNREADABLE
        text, language = parsed
        if not text.strip():
            return None, SKIP_EMPTY
    elif tier == TIER_DATA:
        text = _csv_sample(text)
    elif tier == TIER_TEXT:
        name = path.lower().rsplit("/", 1)[-1]
        language = _NAME_LANGUAGES.get(name) or _TEXT_LANGUAGES.get(PurePosixPath(name).suffix, "text")

    return Document(
        page_content=text,
        metadata={
            **metadata,
            "filename": path,
            "source": path,
            "file_path": path,
            "language": language,
            "file_type": "code" if tier == TIER_CODE else tier,
            "tier": tier,
        },
    ), None


def _notebook_text(raw: str) -> tuple[str, str] | None:
    """Code and Markdown cells with their outputs DROPPED (outputs hold data, plots and secrets: S19)."""
    try:
        notebook = json.loads(raw)
        cells = notebook["cells"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(cells, list):
        return None
    language = ((notebook.get("metadata") or {}).get("kernelspec") or {}).get("language") or "python"
    parts = []
    for number, cell in enumerate(cells, 1):
        if not isinstance(cell, dict) or cell.get("cell_type") not in ("code", "markdown"):
            continue
        source = cell.get("source", "")
        source = "".join(source) if isinstance(source, list) else str(source)
        if not source.strip():
            continue
        label = "[markdown] " if cell["cell_type"] == "markdown" else ""
        parts.append(f"# %% {label}cell {number}\n{source}")
    return "\n\n".join(parts), str(language)


def _csv_sample(text: str) -> str:
    """The header and the first rows only, never the whole file (S20)."""
    lines = text.splitlines()[: DATA_SAMPLE_ROWS + 1]
    kept, size = [], 0
    for line in lines:
        size += len(line.encode("utf-8")) + 1
        if size > DATA_SAMPLE_MAX_BYTES and kept:
            break
        kept.append(line[:MAX_LINE_LENGTH])
    return "\n".join(kept)
