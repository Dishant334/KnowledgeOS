# Design: an ALLOW-LIST. A file is read only if its extension or name is in a
# table below; everything else is skipped. Forgetting a type therefore fails
# safe (skipped) instead of letting something dangerous through.
#
# Stdlib only on purpose: loaders, the zip reader and (mirrored by hand) the
# browser all depend on these rules, so this module must not import the app.
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

# --- Tiers: how a file is read and chunked (Plan-Codebase.md section 2.5) ----
TIER_CODE = "code"          # tree-sitter: one chunk per function/class
TIER_TEXT = "text"          # structure-aware text splitting (Markdown, config, web)
TIER_NOTEBOOK = "notebook"  # .ipynb: code + markdown cells, outputs dropped (S19)
TIER_DATA = "data"          # .csv/.tsv: header + first rows only, never in full (S20)

# Tier 1: extension -> language name (also used as chunk metadata).
TIER1_CODE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
}

# Tier 2: text and config, by extension...
TIER2_TEXT: frozenset[str] = frozenset(
    {
        ".html", ".css", ".scss",
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
        ".sql", ".sh",
        ".txt", ".md", ".rst",
    }
)
# ...and by exact (lower-case) file name, for files with no useful extension.
TIER2_TEXT_NAMES: frozenset[str] = frozenset(
    {"dockerfile", "makefile", "requirements.txt", ".gitignore", ".env.example", ".env.sample", ".env.template"}
)

TIER3_NOTEBOOK: frozenset[str] = frozenset({".ipynb"})
TIER4_DATA: frozenset[str] = frozenset({".csv", ".tsv"})

# --- Skip rules --------------------------------------------------------------
# Directory names (any depth). Only DIRECTORIES count: a file "build.py" is fine.
IGNORED_DIRS: frozenset[str] = frozenset(
    {
        "node_modules", ".git", "venv", ".venv", "env", "dist", "build", "target", "out",
        "__pycache__", ".idea", ".vscode", "vendor",
        ".next", ".nuxt", "coverage", ".pytest_cache", ".mypy_cache", ".gradle", ".tox", "site-packages",
    }
)
# File names (exact, lower-case) and glob patterns that are noise, not source (S10, S21).
IGNORED_FILE_NAMES: frozenset[str] = frozenset(
    {
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
        "pipfile.lock", "composer.lock", "cargo.lock", ".ds_store",
    }
)
IGNORED_FILE_PATTERNS: tuple[str, ...] = ("*.min.js", "*.min.css", "*.map")

# Files that probably hold secrets (S6): skipped, never stored or sent to an LLM.
# Examples such as `.env.example` are allowed (they are in TIER2_TEXT_NAMES).
SECRET_FILE_PATTERNS: tuple[str, ...] = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*", "credentials*",
)

# --- Caps (S1, S9, S10, S17) ------------------------------------------------
MAX_FILE_BYTES: dict[str, int] = {
    TIER_CODE: 1_000_000,
    TIER_TEXT: 200_000,        # also caps .json (S21)
    TIER_NOTEBOOK: 5_000_000,  # outputs are dropped after parsing
    TIER_DATA: 5_000_000,      # only a small sample is ever kept
}
MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024  # total bytes after unzipping
MAX_FILES = 500                          # members read from one zip
MAX_LINE_LENGTH = 2_000                  # longer lines mean minified/generated code
MAX_PATH_LENGTH = 300
DATA_SAMPLE_ROWS = 30                    # first N rows of a .csv/.tsv
DATA_SAMPLE_MAX_BYTES = 20_000           # hard byte cap on that sample

# Skip reasons, so the UI can say WHY files were left out.
SKIP_UNSAFE_PATH = "unsafe_path"
SKIP_IGNORED_DIR = "ignored_dir"
SKIP_IGNORED_FILE = "ignored_file"
SKIP_SECRET_FILE = "secret_file"
SKIP_UNSUPPORTED = "unsupported_type"

_DRIVE_LETTER = re.compile(r"^[A-Za-z]:")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class Classification:
    """What to do with one path. `accepted` is False when `skip_reason` is set."""

    accepted: bool
    tier: str | None = None
    language: str | None = None
    skip_reason: str | None = None


def _to_slashes(name: str) -> str:
    # Windows-made zips use backslashes; treat them as separators.
    return name.replace("\\", "/")


def is_safe_member_name(name: str) -> bool:
    """S2: reject names that could escape the project root or are malformed.

    We never write zip members to disk, but `file_path` is stored and shown, so
    it must be clean. Rejects: empty, control chars/NUL, absolute paths (`/x`,
    `\\x`, `\\\\server\\share`), drive letters, any `..` segment, over-long names.
    """
    if not name or not name.strip() or len(name) > MAX_PATH_LENGTH:
        return False
    if _CONTROL_CHARS.search(name):
        return False
    path = _to_slashes(name)
    if path.startswith("/") or _DRIVE_LETTER.match(path):
        return False
    return ".." not in path.split("/")


def normalize_path(name: str) -> str:
    """Unify separators and drop `.`/empty segments. Call only after is_safe_member_name."""
    parts = [p for p in _to_slashes(name).split("/") if p not in ("", ".")]
    return "/".join(parts)


def _matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def _ignored_reason(path: str) -> str | None:
    parts = normalize_path(path).lower().split("/")
    if any(part in IGNORED_DIRS for part in parts[:-1]):
        return SKIP_IGNORED_DIR
    filename = parts[-1]
    if filename in IGNORED_FILE_NAMES or _matches_any(filename, IGNORED_FILE_PATTERNS):
        return SKIP_IGNORED_FILE
    return None


def is_ignored_path(path: str) -> bool:
    """True for build/vendor folders, lock files and minified/map files."""
    return _ignored_reason(path) is not None


def _is_secret_name(filename: str) -> bool:
    if filename in TIER2_TEXT_NAMES:  # `.env.example` is documentation, not a secret
        return False
    return _matches_any(filename, SECRET_FILE_PATTERNS)


def language_for(path: str) -> str | None:
    """The language of a Tier 1 code file, or None."""
    return TIER1_CODE.get(PurePosixPath(normalize_path(path).lower()).suffix)


def classify(path: str) -> Classification:
    """Decide what to do with a project file. Order matters: safety first."""
    if not is_safe_member_name(path):
        return Classification(False, skip_reason=SKIP_UNSAFE_PATH)

    clean = normalize_path(path)
    ignored = _ignored_reason(clean)
    if ignored:
        return Classification(False, skip_reason=ignored)

    filename = clean.lower().rsplit("/", 1)[-1]
    if _is_secret_name(filename):
        return Classification(False, skip_reason=SKIP_SECRET_FILE)

    suffix = PurePosixPath(filename).suffix
    if suffix in TIER1_CODE:
        return Classification(True, tier=TIER_CODE, language=TIER1_CODE[suffix])
    if suffix in TIER3_NOTEBOOK:
        return Classification(True, tier=TIER_NOTEBOOK)
    if suffix in TIER4_DATA:
        return Classification(True, tier=TIER_DATA)
    if suffix in TIER2_TEXT or filename in TIER2_TEXT_NAMES:
        return Classification(True, tier=TIER_TEXT)
    return Classification(False, skip_reason=SKIP_UNSUPPORTED)
