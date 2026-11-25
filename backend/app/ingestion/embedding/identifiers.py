# app/ingestion/embedding/identifiers.py
#
# Identifier-aware keyword search (Stage 7, code mode only).
#
# BM25 compares WORDS. To it, `take_token` and `TokenBucket` are each one single word, so a question about
# "the token bucket" shares no keyword with the code. The fix: before BM25 reads a text, ADD the parts of every
# identifier to the end of the text ("take_token" -> also "take token"). The original identifier stays, so an exact
# question still matches exactly. BM25 ignores word order, so appending is enough. Only the text BM25 reads is
# changed: the chunk text that is stored, shown and cited is never touched.
#
# Documents and queries MUST go through the same function, otherwise they stop matching each other.
# It is switched on only where the chat is a code chat (see `splitting` below).

import re
from contextlib import contextmanager
from contextvars import ContextVar

# a name: letters, digits and underscores, starting with a letter or underscore
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# where a name breaks into words: an underscore, or a lower/digit -> Upper step (getUser), or the end of an acronym (HTTPServer)
_BREAK = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

_enabled: ContextVar[bool] = ContextVar("identifier_splitting", default=False)


def _parts(name: str) -> list[str]:
    parts = [p.lower() for p in _BREAK.split(name) if p]
    return [p for p in parts if len(p) >= 2] if len(parts) > 1 else []


def expand_identifiers(text: str) -> str:
    """`text` followed by the parts of every identifier in it; unchanged when no identifier has parts."""
    extra: list[str] = []
    for match in _NAME.finditer(text):
        extra.extend(_parts(match.group()))
    return f"{text}\n{' '.join(extra)}" if extra else text


def splitting_enabled() -> bool:
    return _enabled.get()


@contextmanager
def splitting(enabled: bool):
    """Turn identifier splitting on/off for the BM25 calls made inside the `with` block (this thread/task only)."""
    token = _enabled.set(enabled)
    try:
        yield
    finally:
        _enabled.reset(token)
