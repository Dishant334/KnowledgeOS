# CODEBASE-FEATURE (Stage 6): AST chunking with tree-sitter.
#
# All UNIT tests: no database, no Qdrant, no models. They run the real tree-sitter grammars.
# The invariants every language must keep:
#   * no line of the source is lost or duplicated (the chunks, in order, hold every non-blank line exactly once)
#   * the chunk's start_line..end_line really are the lines of the source it holds
#   * a function / class is never cut in half when it fits in a chunk
#   * a file that cannot be parsed falls back to the Stage 2 splitter instead of failing
import pytest
from langchain_core.documents import Document

from app.ingestion.chunking import ast_chunker
from app.ingestion.chunking.ast_chunker import MAX_AST_BYTES, ast_chunks
from app.ingestion.chunking.model import ChunkingConfig
from app.ingestion.chunking.strategies import CodeChunkingStrategy

PY = '''import os
import sys

CONSTANT = 1


def alpha(x):
    """Add one."""
    return x + 1


# a comment about beta
@decorator
def beta(y):
    if y:
        return 2
    return 3


class Gamma:
    """Class doc."""

    def one(self):
        return 1

    def two(self):
        return 2
'''

JS = '''import { a } from "./a.js"

export function alpha(x) {
  return x + 1
}

const beta = (y) => {
  return y * 2
}

class Gamma {
  one() {
    return 1
  }

  two() {
    return 2
  }
}
'''

TS = '''interface Shape {
  area(): number
}

export function alpha(x: number): number {
  return x + 1
}

class Gamma implements Shape {
  area(): number {
    return 1
  }
}
'''

TSX = '''import React from "react"

export function Alpha({ name }: { name: string }) {
  return <div className="a">{name}</div>
}

export const Beta = () => <span>beta</span>
'''

JAVA = '''package demo;

import java.util.List;

public class Gamma {
    private int count = 0;

    public int one() {
        return 1;
    }

    public int two() {
        return 2;
    }
}
'''

C = '''#include <stdio.h>

struct point {
    int x;
    int y;
};

int alpha(int x) {
    return x + 1;
}

static int beta(int y) {
    return y * 2;
}
'''

CPP = '''#include <vector>

namespace demo {

class Gamma {
public:
    int one() { return 1; }
    int two() { return 2; }
};

int alpha(int x) {
    return x + 1;
}

}  // namespace demo
'''

SAMPLES = [
    ("python", PY, "mod.py"), ("javascript", JS, "mod.js"), ("typescript", TS, "mod.ts"), ("typescript", TSX, "App.tsx"),
    ("java", JAVA, "Gamma.java"), ("c", C, "mod.c"), ("cpp", CPP, "mod.cpp"),
]


def chunk(source, language="python", path="mod.py", size=40, min_tokens=0, header=False):
    return ast_chunks(source, language, path, chunk_size=size, min_tokens=min_tokens, header=header)


def assert_nothing_lost_and_lines_exact(source, chunks):
    wanted = [line for line in source.splitlines() if line.strip()]
    got = [line for c in chunks for line in c.text.splitlines() if line.strip()]
    assert got == wanted                                                    # every non-blank line, once, in order
    lines = source.replace("\r\n", "\n").split("\n")
    previous_end = 0
    for c in chunks:
        assert 1 <= c.start_line <= c.end_line <= len(lines) and c.start_line > previous_end
        assert "\n".join(lines[c.start_line - 1:c.end_line]).rstrip() == c.text.replace("\r\n", "\n")   # the lines it claims ARE its text
        previous_end = c.end_line


# --- every language -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("language,source,path", SAMPLES)
def test_every_language_parses_and_keeps_every_line_exactly_once(language, source, path):
    chunks = chunk(source, language, path, size=30)
    assert chunks is not None and len(chunks) >= 2
    assert_nothing_lost_and_lines_exact(source, chunks)


@pytest.mark.parametrize("language,source,path", SAMPLES)
def test_a_small_file_is_one_chunk_holding_the_whole_file(language, source, path):
    [only] = chunk(source, language, path, size=5000, min_tokens=0)       # it fits in one chunk, so it stays one
    assert only.text == source.rstrip()
    assert (only.start_line, only.end_line) == (1, len(source.rstrip().splitlines()))


# --- python in detail --------------------------------------------------------------------------------------------------


def test_each_function_is_its_own_chunk_and_never_cut_in_half():
    chunks = chunk(PY, size=60)
    texts = [c.text for c in chunks]
    holder = [t for t in texts if "def alpha" in t]
    assert len(holder) == 1 and "return x + 1" in holder[0] and "def beta" not in holder[0]
    beta = [t for t in texts if "def beta" in t]
    assert len(beta) == 1 and "return 3" in beta[0]


def test_a_comment_and_a_decorator_stay_with_the_function_they_describe():
    chunks = chunk(PY, size=60)
    [beta] = [c for c in chunks if "def beta" in c.text]
    assert "# a comment about beta" in beta.text and "@decorator" in beta.text
    assert beta.text.splitlines()[0].startswith("# a comment")


def test_an_oversized_class_is_split_into_its_methods():
    chunks = chunk(PY, size=22)
    one = [c for c in chunks if "def one" in c.text]
    two = [c for c in chunks if "def two" in c.text]
    assert len(one) == 1 and len(two) == 1 and one[0] is not two[0]
    assert "def two" not in one[0].text and "def one" not in two[0].text
    assert_nothing_lost_and_lines_exact(PY, chunks)


def test_tiny_neighbours_are_merged_up_to_the_minimum_but_never_past_the_chunk_size():
    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    spread = chunk(PY, size=60, min_tokens=0)                            # 6 chunks: os, sys, CONSTANT, alpha, beta, Gamma
    merged = chunk(PY, size=60, min_tokens=40)
    assert len(spread) == 6 and len(merged) < len(spread)
    assert all(len(encoding.encode(c.text)) <= 60 for c in merged)
    assert_nothing_lost_and_lines_exact(PY, merged)


def test_a_trailing_scrap_is_folded_into_the_chunk_before_it():
    chunks = chunk(JS, "javascript", "mod.js", size=60, min_tokens=40)
    assert all(c.text.strip() not in ("}", "};", ")") for c in chunks)          # no chunk that is only a closing bracket


def test_symbols_name_what_each_chunk_holds():
    chunks = chunk(PY, size=22)                                          # small enough that beta and Gamma are cut up
    symbols = [c.symbols for c in chunks]
    for wanted in (["alpha"], ["beta"], ["Gamma.one"], ["Gamma.two"]):
        assert wanted in symbols, symbols
    assert not any("beta.beta" in s for s in symbols)                    # a decorated function is named once


def test_names_are_found_in_every_language():
    names = {
        "javascript": chunk(JS, "javascript", "mod.js", size=30),
        "typescript": chunk(TS, "typescript", "mod.ts", size=30),
        "java": chunk(JAVA, "java", "Gamma.java", size=30),
        "c": chunk(C, "c", "mod.c", size=30),
        "cpp": chunk(CPP, "cpp", "mod.cpp", size=30),
    }
    for language, chunks in names.items():
        symbols = {s for c in chunks for s in c.symbols}
        assert any("alpha" in s or "Gamma" in s for s in symbols), (language, symbols)
    assert any("alpha" in c.symbols for c in names["c"]) and any("beta" in c.symbols for c in names["c"])


# --- the header -------------------------------------------------------------------------------------------------------------


def test_the_header_names_the_file_and_the_symbols_and_does_not_move_the_line_numbers():
    plain = chunk(PY, size=60)
    headed = chunk(PY, size=60, header=True, path="pkg/mod.py")
    assert len(plain) == len(headed)
    for p, h in zip(plain, headed):
        first, _, rest = h.text.partition("\n")
        assert first.startswith("# File: pkg/mod.py") and rest == p.text
        assert (h.start_line, h.end_line) == (p.start_line, p.end_line)        # the header is not a line of the source
    assert any("alpha" in h.text.splitlines()[0] for h in headed)


def test_the_header_uses_the_comment_style_of_the_language():
    assert chunk(JS, "javascript", "a/b.js", size=60, header=True)[0].text.startswith("// File: a/b.js")
    assert chunk(C, "c", "x.c", size=60, header=True)[0].text.startswith("// File: x.c")


def test_without_a_header_the_text_is_exactly_the_source():
    assert all("File:" not in c.text for c in chunk(PY, size=60))


# --- awkward input -----------------------------------------------------------------------------------------------------------


def test_non_ascii_text_keeps_exact_lines():
    source = 'def saluer():\n    return "café ☕ — ça va ? 😀"\n\n\ndef autre():\n    return "naïve"\n'
    chunks = chunk(source, size=20)                                      # the whole file is 27 tokens, each function fits
    assert len(chunks) == 2 and "café ☕ — ça va ? 😀" in chunks[0].text
    assert_nothing_lost_and_lines_exact(source, chunks)


def test_windows_line_endings():
    source = PY.replace("\n", "\r\n")
    chunks = chunk(source, size=60)
    assert any("def alpha" in c.text for c in chunks)
    assert_nothing_lost_and_lines_exact(source, chunks)


def test_an_oversized_function_is_split_inside_its_body_without_losing_lines():
    body = "".join(f"    value_{i} = compute({i})\n" for i in range(80))
    source = f"def long_function():\n{body}    return value_79\n"
    chunks = chunk(source, size=60)
    assert len(chunks) > 3
    assert_nothing_lost_and_lines_exact(source, chunks)


def test_one_enormous_line_does_not_loop_forever_and_is_kept_whole():
    source = "DATA = [" + ", ".join(str(i) for i in range(600)) + "]\n"
    chunks = chunk(source, size=50)
    assert [c.text for c in chunks] == [source.rstrip()]


def test_whitespace_only_source_has_no_chunks():
    assert chunk("   \n\n") == []


def test_only_comments_still_works():
    source = "# one\n# two\n"
    [only] = chunk(source, size=100)
    assert only.text == "# one\n# two"


# --- when the AST cannot be used: None (the caller falls back) -------------------------------------------------------------------------


def test_a_file_with_a_syntax_error_is_not_chunked_by_the_ast():
    assert chunk("def broken(:\n    return\n\ndef fine():\n    pass\n") is None


def test_an_unsupported_language_is_not_chunked_by_the_ast():
    assert chunk("puts 'hi'\n", "ruby", "a.rb") is None


def test_a_huge_file_is_left_to_the_fallback():
    assert chunk("x = 1\n" * (MAX_AST_BYTES // 6 + 10)) is None


def test_a_parser_crash_is_not_fatal(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("grammar exploded")

    monkeypatch.setattr(ast_chunker, "_parse", boom)
    assert chunk(PY) is None


# --- the strategy: AST first, the Stage 2 splitter as the safety net -------------------------------------------------------------------------


def doc(source, path="mod.py", language="python"):
    return Document(page_content=source, metadata={"file_path": path, "language": language, "source": path, "document_id": "1"})


CONFIG = ChunkingConfig(chunk_size=60, chunk_overlap=0)


def test_the_strategy_uses_the_ast_and_labels_its_chunks():
    chunks = CodeChunkingStrategy(CONFIG, mode="ast").split(doc(PY))
    assert chunks and all(c.metadata["chunker"] == "ast" for c in chunks)
    assert all(c.metadata["file_path"] == "mod.py" and c.metadata["language"] == "python" for c in chunks)
    assert any("alpha" in c.metadata["symbols"] for c in chunks)
    assert all(isinstance(c.metadata["start_line"], int) and isinstance(c.metadata["end_line"], int) for c in chunks)


def test_a_syntax_error_falls_back_to_the_splitter_and_still_produces_chunks():
    broken = "def broken(:\n    return\n" + "x = 1\n" * 80
    chunks = CodeChunkingStrategy(CONFIG, mode="ast").split(doc(broken))
    assert len(chunks) >= 2 and all(c.metadata["chunker"] == "splitter" for c in chunks)
    assert all("start_line" in c.metadata for c in chunks)


def test_splitter_mode_is_exactly_the_stage_2_behaviour():
    from app.ingestion.chunking.strategies import add_line_numbers
    from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

    source = PY * 6
    expected = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base", chunk_size=60, chunk_overlap=0,
        separators=RecursiveCharacterTextSplitter.get_separators_for_language(Language.PYTHON), strip_whitespace=False,
    ).split_documents([doc(source)])
    add_line_numbers(source, expected)
    got = CodeChunkingStrategy(CONFIG, mode="splitter").split(doc(source))
    assert [c.page_content for c in got] == [c.page_content for c in expected]
    assert [(c.metadata["start_line"], c.metadata["end_line"]) for c in got] == [(c.metadata["start_line"], c.metadata["end_line"]) for c in expected]
    assert all(c.metadata["chunker"] == "splitter" for c in got)


def test_the_header_option_reaches_the_chunk_text():
    chunks = CodeChunkingStrategy(CONFIG, mode="ast", header=True).split(doc(PY, "pkg/mod.py"))
    assert all(c.page_content.startswith("# File: pkg/mod.py") for c in chunks)


def test_tsx_files_use_the_tsx_grammar():
    chunks = CodeChunkingStrategy(CONFIG, mode="ast").split(doc(TSX, "App.tsx", "typescript"))
    assert chunks and all(c.metadata["chunker"] == "ast" for c in chunks)


def test_the_mode_and_header_come_from_settings_when_not_given():
    from app.core.config import settings

    strategy = CodeChunkingStrategy(CONFIG)
    assert strategy.mode == settings.code_chunker and strategy.header == settings.code_chunk_header
    assert settings.code_chunker in ("ast", "splitter")


def test_settings_refuse_an_unknown_chunker():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(code_chunker="magic")


def test_the_new_chunk_size_floor_must_be_valid():
    with pytest.raises(ValueError):
        ChunkingConfig(code_min_chunk_tokens=-1)
