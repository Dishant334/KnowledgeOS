# app/ingestion/cleaning/normalizers.py

import re
import unicodedata

from langchain_core.documents import Document

from app.ingestion.cleaning.base import DocumentCleaner


class ControlCharacterStripper(DocumentCleaner):
    """
    Removes non-printable control characters that sometimes leak in
    from OCR output or malformed source files (keeps \\n and \\t).
    Runs FIRST so nothing downstream has to deal with raw junk bytes.
    """
    _CONTROL_CHARS = re.compile(
        "[" + "".join(chr(c) for c in range(0, 32) if c not in (9, 10)) + "]"
    )

    def clean(self, document: Document) -> Document:
        text = self._CONTROL_CHARS.sub("", document.page_content)
        return Document(page_content=text, metadata=document.metadata)


class UnicodeNormalizer(DocumentCleaner):
    """
    Normalizes unicode (NFKC) and replaces "smart" characters (curly
    quotes, em/en dashes, non-breaking spaces, BOM) with ASCII-safe
    equivalents, so downstream regex/dedup comparisons behave
    consistently regardless of which app produced the source file.
    """
    _REPLACEMENTS = {
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-",
        "\u00a0": " ",
        "\ufeff": "",
    }

    def clean(self, document: Document) -> Document:
        text = unicodedata.normalize("NFKC", document.page_content)
        for old, new in self._REPLACEMENTS.items():
            text = text.replace(old, new)
        return Document(page_content=text, metadata=document.metadata)


class WhitespaceNormalizer(DocumentCleaner):
    """
    Collapses excessive whitespace/newlines and strips leading/
    trailing whitespace from each line.
    """
    _MULTI_SPACE = re.compile(r"[ \t]{2,}")
    _MULTI_NEWLINE = re.compile(r"\n{3,}")

    def clean(self, document: Document) -> Document:
        text = self._MULTI_SPACE.sub(" ", document.page_content)
        text = self._MULTI_NEWLINE.sub("\n\n", text)
        text = "\n".join(line.strip() for line in text.split("\n")).strip()
        return Document(page_content=text, metadata=document.metadata)