# CODEBASE-FEATURE (Stage 1): unit tests for the codebase file policy.
# Pure unit tests: no database, no Docker, no mocks.
import pytest

from app.ingestion.codebase import policy
from app.ingestion.codebase.policy import (
    TIER_CODE,
    TIER_DATA,
    TIER_NOTEBOOK,
    TIER_TEXT,
    classify,
    is_ignored_path,
    is_safe_member_name,
    language_for,
    normalize_path,
)


# --- is_safe_member_name (S2: path traversal) -------------------------------

@pytest.mark.parametrize(
    "name",
    [
        "../x.py",
        "a/../../x.py",
        "a/b/../../../x.py",
        "..",
        "/etc/passwd",
        "\\windows\\system32\\x.py",
        "C:\\Users\\me\\x.py",
        "c:/x.py",
        "\\\\server\\share\\x.py",
        "src/..\\..\\x.py",
        "",
        "   ",
        "a\x00b.py",
        "a\nb.py",
        "x" * 400 + ".py",
    ],
)
def test_unsafe_member_names_are_rejected(name):
    assert is_safe_member_name(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "main.py",
        "src/app/main.py",
        "src\\app\\main.py",  # Windows-made zips use backslashes: safe once normalised
        "./src/main.py",
        "a/b/c/d.js",
        "my..file.py",  # two dots inside a name are not a traversal
        "README.md",
    ],
)
def test_safe_member_names_are_accepted(name):
    assert is_safe_member_name(name) is True


def test_normalize_path_unifies_separators_and_strips_dot_prefix():
    assert normalize_path("src\\app\\main.py") == "src/app/main.py"
    assert normalize_path("./src//main.py") == "src/main.py"
    assert normalize_path("a/./b.py") == "a/b.py"


# --- language_for / tiers ----------------------------------------------------

@pytest.mark.parametrize(
    "path,language",
    [
        ("a.py", "python"),
        ("a.js", "javascript"),
        ("a.jsx", "javascript"),
        ("a.mjs", "javascript"),
        ("a.cjs", "javascript"),
        ("a.ts", "typescript"),
        ("a.tsx", "typescript"),
        ("A.java", "java"),
        ("a.c", "c"),
        ("a.h", "c"),
        ("a.cpp", "cpp"),
        ("a.hpp", "cpp"),
        ("a.cc", "cpp"),
        ("a.cxx", "cpp"),
        ("src/Main.PY", "python"),  # case-insensitive
    ],
)
def test_language_for_tier1_code(path, language):
    assert language_for(path) == language


@pytest.mark.parametrize("path", ["logo.png", "model.pkl", "notes.docx", "a.exe", "noextension", "x.pdf"])
def test_language_for_unknown_is_none(path):
    assert language_for(path) is None


@pytest.mark.parametrize(
    "path,tier",
    [
        ("main.py", TIER_CODE),
        ("web/App.tsx", TIER_CODE),
        ("index.html", TIER_TEXT),
        ("style.css", TIER_TEXT),
        ("package.json", TIER_TEXT),
        ("config.yaml", TIER_TEXT),
        ("config.yml", TIER_TEXT),
        ("query.sql", TIER_TEXT),
        ("run.sh", TIER_TEXT),
        ("README.md", TIER_TEXT),
        ("notes.txt", TIER_TEXT),
        ("Dockerfile", TIER_TEXT),
        ("api/Dockerfile", TIER_TEXT),
        ("Makefile", TIER_TEXT),
        ("requirements.txt", TIER_TEXT),
        (".gitignore", TIER_TEXT),
        (".env.example", TIER_TEXT),
        ("analysis.ipynb", TIER_NOTEBOOK),
        ("data/train.csv", TIER_DATA),
        ("data/train.tsv", TIER_DATA),
    ],
)
def test_classify_assigns_the_right_tier(path, tier):
    result = classify(path)
    assert result.accepted is True
    assert result.tier == tier
    assert result.skip_reason is None


def test_classify_code_carries_the_language():
    assert classify("src/a.py").language == "python"
    assert classify("README.md").language is None


# --- ignored paths (S10, S21) ------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "node_modules/x/index.js",
        "a/b/node_modules/y.js",
        ".git/config",
        "venv/lib/x.py",
        ".venv/bin/a.py",
        "dist/bundle.js",
        "build/out.js",
        "target/classes/A.java",
        "__pycache__/x.py",
        ".idea/workspace.xml",
        ".vscode/settings.json",
        "vendor/lib.c",
        "package-lock.json",
        "web/yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "app.min.js",
        "static/app.min.css",
        "app.js.map",
        ".DS_Store",
    ],
)
def test_ignored_paths(path):
    assert is_ignored_path(path) is True
    result = classify(path)
    assert result.accepted is False
    assert result.skip_reason in {"ignored_dir", "ignored_file"}


def test_a_file_named_like_an_ignored_dir_is_not_ignored():
    # only DIRECTORY names count; a file called "build.py" or "dist" is fine
    assert is_ignored_path("build.py") is False
    assert classify("src/build.py").accepted is True


def test_ordinary_paths_are_not_ignored():
    assert is_ignored_path("src/app/main.py") is False


# --- secrets (S6) ------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".env.production",
        "backend/.env",
        "server.pem",
        "certs/private.key",
        "id_rsa",
        "id_rsa.pub",
        "id_ed25519",
        "credentials.json",
        "credentials",
        "keystore.p12",
        "cert.pfx",
    ],
)
def test_secret_looking_files_are_skipped(path):
    result = classify(path)
    assert result.accepted is False
    assert result.skip_reason == "secret_file"


def test_env_example_is_allowed_but_env_is_not():
    assert classify(".env.example").accepted is True
    assert classify(".env.sample").accepted is True
    assert classify(".env").skip_reason == "secret_file"


# --- everything else is skipped (allow-list) ---------------------------------

@pytest.mark.parametrize("path", ["logo.png", "model.pkl", "weights.h5", "net.pt", "m.onnx", "inner.zip", "doc.pdf", "a.exe", "noext"])
def test_unsupported_types_are_skipped(path):
    result = classify(path)
    assert result.accepted is False
    assert result.skip_reason == "unsupported_type"


def test_unsafe_path_is_reported_as_unsafe_not_unsupported():
    result = classify("../../x.py")
    assert result.accepted is False
    assert result.skip_reason == "unsafe_path"


# --- caps --------------------------------------------------------------------

def test_size_caps_have_the_documented_values():
    assert policy.MAX_FILE_BYTES[TIER_CODE] == 1_000_000
    assert policy.MAX_FILE_BYTES[TIER_TEXT] == 200_000
    assert policy.MAX_ZIP_UNCOMPRESSED == 50 * 1024 * 1024
    assert policy.MAX_FILES == 500
    assert policy.MAX_LINE_LENGTH > 0
    assert policy.DATA_SAMPLE_ROWS == 30


def test_every_tier_has_a_size_cap():
    for tier in (TIER_CODE, TIER_TEXT, TIER_NOTEBOOK, TIER_DATA):
        assert policy.MAX_FILE_BYTES[tier] > 0


def test_tier_tables_do_not_overlap():
    code = set(policy.TIER1_CODE)
    text = set(policy.TIER2_TEXT)
    assert code.isdisjoint(text)
    assert policy.TIER3_NOTEBOOK.isdisjoint(code | text)
    assert policy.TIER4_DATA.isdisjoint(code | text | policy.TIER3_NOTEBOOK)
