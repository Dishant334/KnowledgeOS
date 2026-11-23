# app/ingestion/chunking/ast_chunker.py
# CODEBASE-FEATURE (Stage 6): chunk source code along its SYNTAX TREE instead of along keyword patterns.
"""
WHAT AN AST IS
tree-sitter parses a file into a tree: a module holds functions and classes, a class holds methods, a function holds
statements. Every node knows exactly where it starts and ends. Stage 2's splitter only looked for patterns such as
"\\ndef " and could not tell where a method (indented with 4 spaces) began; the tree can.

WHAT THIS MODULE DOES
1. Cuts the file into BLOCKS, one per top-level node. A block runs from the end of the previous node to the end of this
   one, so a comment or a decorator above a function belongs to that function (it is "trivia" that attaches downwards).
2. A block that fits in `chunk_size` tokens stays whole. A bigger one (a large class or function) is cut again along ITS
   children (a class into its methods, a function into its statements), and so on. A leaf that is still too big
   (a huge literal) is cut by lines.
3. Neighbouring small blocks of the same scope (imports, constants, tiny functions) are merged until they reach
   `min_tokens`, so we do not create hundreds of 20-token chunks.
4. Each chunk's text is exactly the source lines it covers (leading blank lines and trailing whitespace are trimmed;
   indentation is kept) and its start_line / end_line come straight from the tree, with no text search.
5. Optionally a one-line header is put in front of the text:  "# File: path/to/mod.py | Class.method".

WHEN IT SAYS "I CANNOT": ast_chunks returns None (never raises), and the caller falls back to the Stage 2 splitter:
an unsupported language, a missing grammar package, a file with a syntax error, a file over MAX_AST_BYTES, any crash.
One bad file must never fail an upload (policy S9).
"""

import logging
from bisect import bisect_left
from dataclasses import dataclass, field
from functools import lru_cache

import tiktoken

logger = logging.getLogger(__name__)

MAX_AST_BYTES = 1_000_000     # the policy's cap for one code file; bigger files are left to the splitter
MAX_DEPTH = 8                 # how many times a block may be cut again (a guard against pathological nesting)
MAX_SYMBOLS = 8               # symbols recorded per chunk

# our language name -> (the grammar's Python package, the function that returns the grammar)
_GRAMMARS = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),           # .tsx has JSX, which needs its own grammar
    "java": ("tree_sitter_java", "language"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
}
_NAME_NODE_TYPES = {"identifier", "field_identifier", "type_identifier", "property_identifier", "qualified_identifier",
                    "destructor_name", "operator_name"}


@dataclass
class CodeChunk:
    text: str
    start_line: int                    # 1-based, inclusive; the header (if any) is NOT a line of the source
    end_line: int
    symbols: list[str] = field(default_factory=list)       # what the chunk holds: ["alpha"], ["Gamma.one"], ...


@dataclass
class _Unit:
    lo: int                            # byte offsets in the source
    hi: int
    scope: tuple[str, ...]             # the classes/functions this unit sits inside
    names: list[str]
    tokens: int


@lru_cache(maxsize=None)
def _parser(key: str):
    """The parser for one grammar, built once. None if the grammar package is not installed."""
    try:
        import importlib

        from tree_sitter import Language, Parser

        module_name, function_name = _GRAMMARS[key]
        language = Language(getattr(importlib.import_module(module_name), function_name)())
        return Parser(language)
    except Exception:
        logger.warning("tree-sitter grammar for %s is not available; using the splitter", key, exc_info=True)
        return None


def _parse(data: bytes, key: str):
    parser = _parser(key)
    return parser.parse(data) if parser is not None else None


def ast_chunks(
    source: str,
    language: str,
    file_path: str,
    *,
    chunk_size: int,
    min_tokens: int,
    encoding_name: str = "cl100k_base",
    header: bool = False,
) -> list[CodeChunk] | None:
    """The chunks of one source file, or None when the syntax tree cannot be used (the caller falls back)."""
    key = "tsx" if language == "typescript" and file_path.lower().endswith(".tsx") else language
    if key not in _GRAMMARS:
        return None
    if not source.strip():
        return []
    data = source.encode("utf-8")
    if len(data) > MAX_AST_BYTES:
        return None
    try:
        tree = _parse(data, key)
        if tree is None or tree.root_node.has_error:           # a syntax error: do not guess where things end
            return None
        builder = _Builder(data, chunk_size, min(min_tokens, chunk_size), tiktoken.get_encoding(encoding_name))
        return builder.run(tree.root_node, file_path, header, key == "python")
    except Exception:
        logger.warning("AST chunking failed for %s (%s); using the splitter", file_path, language, exc_info=True)   # never the code itself
        return None


class _Builder:
    def __init__(self, data: bytes, chunk_size: int, min_tokens: int, encoding):
        self.data = data
        self.chunk_size = chunk_size
        self.min_tokens = min_tokens
        self.encoding = encoding
        self.newline_at = [i for i, byte in enumerate(data) if byte == 10]

    # --- measuring ---------------------------------------------------------------------------------------------

    def tokens(self, lo: int, hi: int) -> int:
        return len(self.encoding.encode(self.data[lo:hi].decode("utf-8", errors="replace")))

    def line_of(self, byte: int) -> int:
        return bisect_left(self.newline_at, byte) + 1               # newlines before this byte, plus one

    # --- the tree -> units -------------------------------------------------------------------------------------

    @staticmethod
    def _text(node) -> str | None:
        return node.text.decode("utf-8", errors="replace") if node is not None else None

    def _name_of(self, node, depth: int = 0) -> str | None:
        """The name a definition introduces (function, class, method, const f = ...), if it has one."""
        if node is None or depth > 4:
            return None
        kind = node.type
        if kind == "decorated_definition":
            return self._name_of(node.child_by_field_name("definition"), depth + 1)
        if kind == "export_statement":
            return self._name_of(node.child_by_field_name("declaration"), depth + 1)
        if kind in ("lexical_declaration", "variable_declaration"):
            for child in node.named_children:
                if child.type == "variable_declarator":
                    return self._text(child.child_by_field_name("name"))
            return None
        name = node.child_by_field_name("name")
        if name is not None:
            return self._text(name)
        declarator = node.child_by_field_name("declarator")        # C and C++ functions hide their name in the declarator
        while declarator is not None and declarator.type not in _NAME_NODE_TYPES:
            declarator = declarator.child_by_field_name("declarator") or (declarator.named_children[0] if declarator.named_children else None)
        return self._text(declarator)

    @staticmethod
    def _members(node):
        """The children a too-big node is cut along, or [] if there is nothing to cut along."""
        body = node.child_by_field_name("body")
        if body is not None:                                        # a class body, a function body, a namespace body
            return [c for c in body.children if c.type not in ("{", "}")]     # the braces stay with the header / the last member
        wrapped = node.child_by_field_name("definition") or node.child_by_field_name("declaration")
        if wrapped is not None:
            return [wrapped]                                        # "@decorator def f", "export function f": keep the prefix with it
        return []                                                   # a statement or expression: never cut in the middle of it

    @staticmethod
    def _blocks(children, lo: int, hi: int):
        """(start, end, node) per non-comment child; each block starts where the previous ended, so comments attach DOWNWARDS."""
        blocks, cursor = [], lo
        for child in children:
            if "comment" in child.type or child.end_byte <= cursor:
                continue
            if child.type in (";", ",") and blocks:                  # the ";" of "};" belongs to the node before it
                blocks[-1] = (blocks[-1][0], child.end_byte, blocks[-1][2])
                cursor = child.end_byte
                continue
            blocks.append((cursor, child.end_byte, child))
            cursor = child.end_byte
        if cursor < hi:                                              # trailing comments / closing text join the last block
            if blocks:
                blocks[-1] = (blocks[-1][0], hi, blocks[-1][2])
            else:
                blocks.append((lo, hi, None))
        return blocks

    def _split(self, lo: int, hi: int, node, scope: tuple[str, ...], depth: int) -> list[_Unit]:
        count = self.tokens(lo, hi)
        name = self._name_of(node) if node is not None else None
        names = [".".join(scope + (name,))] if name else []
        if count <= self.chunk_size:
            return [_Unit(lo, hi, scope, names, count)]
        members = self._members(node) if node is not None and depth < MAX_DEPTH else []
        blocks = self._blocks(members, lo, hi) if members else []
        if not blocks:                                               # nothing to cut along (a leaf, or too deep): cut by lines
            return self._split_lines(lo, hi, scope, names)
        is_wrapper = node.child_by_field_name("body") is None         # "@decorator def f" / "export function f": the wrapped
        inner = scope if is_wrapper else scope + ((name,) if name else ())   # definition names itself, so the wrapper adds no scope
        units: list[_Unit] = []
        first_member = blocks[0][2].start_byte if blocks[0][2] is not None else lo
        cut = self.data.rfind(b"\n", lo, first_member) + 1            # the start of the first member's LINE (keeps its indentation)
        if cut > lo:                                                 # "class Gamma:" / "def f(x):" / decorators above the first member
            units.append(_Unit(lo, cut, inner, [], self.tokens(lo, cut)))
            blocks[0] = (cut, blocks[0][1], blocks[0][2])
        for block_lo, block_hi, child in blocks:
            units.extend(self._split(block_lo, block_hi, child, inner, depth + 1))
        return units

    def _split_lines(self, lo: int, hi: int, scope: tuple[str, ...], names: list[str]) -> list[_Unit]:
        """Last resort for a leaf that is too big (a huge literal): cut between lines. One enormous line stays whole."""
        units, start, used = [], lo, 0
        offset = lo
        for line in self.data[lo:hi].decode("utf-8", errors="replace").splitlines(keepends=True):
            size = len(line.encode("utf-8"))
            cost = len(self.encoding.encode(line))
            if used and used + cost > self.chunk_size:
                units.append(_Unit(start, offset, scope, list(names), used))
                start, used = offset, 0
            offset += size
            used += cost
        units.append(_Unit(start, hi, scope, list(names), used))
        return units

    # --- merging and writing -----------------------------------------------------------------------------------

    def _join(self, a: _Unit, b: _Unit) -> _Unit:
        return _Unit(a.lo, b.hi, a.scope, a.names + [n for n in b.names if n not in a.names], self.tokens(a.lo, b.hi))

    def _merge(self, units: list[_Unit]) -> list[_Unit]:
        merged: list[_Unit] = []
        for unit in units:                                           # 1. small neighbours of the same scope, up to min_tokens
            last = merged[-1] if merged else None
            if last and last.scope == unit.scope and last.tokens < self.min_tokens and last.tokens + unit.tokens <= self.chunk_size:
                joined = self._join(last, unit)
                if joined.tokens <= self.chunk_size:
                    merged[-1] = joined
                    continue
            merged.append(unit)
        result: list[_Unit] = []
        for unit in merged:                                          # 2. a scrap (a lone "}") is folded into the chunk before it
            last = result[-1] if result else None
            if last and last.scope == unit.scope and unit.tokens < self.min_tokens // 2 and last.tokens + unit.tokens <= self.chunk_size:
                joined = self._join(last, unit)
                if joined.tokens <= self.chunk_size:
                    result[-1] = joined
                    continue
            result.append(unit)
        return result

    def _chunk(self, unit: _Unit, file_path: str, comment: str, header: bool) -> CodeChunk | None:
        raw = self.data[unit.lo:unit.hi].decode("utf-8", errors="replace")
        stripped = raw.lstrip()
        if not stripped:
            return None
        lead = len(raw) - len(stripped)
        line_start = raw.rfind("\n", 0, lead) + 1                    # keep the indentation of the first line, drop blank lines above it
        text = raw[line_start:].rstrip()
        first_byte = unit.lo + len(raw[:line_start].encode("utf-8"))
        last_byte = first_byte + len(text.encode("utf-8")) - 1
        symbols = unit.names[:MAX_SYMBOLS]
        if header:
            label = f"{comment} File: {file_path}"
            if symbols:
                shown = ", ".join(symbols[:3]) + (f" +{len(symbols) - 3} more" if len(symbols) > 3 else "")
                label += f" | {shown}"
            text = f"{label}\n{text}"
        return CodeChunk(text=text, start_line=self.line_of(first_byte), end_line=self.line_of(last_byte), symbols=symbols)

    def run(self, root, file_path: str, header: bool, hash_comments: bool) -> list[CodeChunk]:
        units: list[_Unit] = []
        for lo, hi, child in self._blocks(list(root.children), 0, len(self.data)):
            units.extend(self._split(lo, hi, child, (), 1))
        whole = self.tokens(0, len(self.data))
        if whole <= self.chunk_size:                                 # nothing to gain by cutting a small file
            names = [n for u in units for n in u.names]
            units = [_Unit(0, len(self.data), (), list(dict.fromkeys(names)), whole)]
        comment = "#" if hash_comments else "//"
        chunks = (self._chunk(u, file_path, comment, header) for u in self._merge(units))
        return [c for c in chunks if c is not None]
