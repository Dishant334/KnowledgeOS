# app/ingestion/cleaning/structural.py

import re

from langchain_core.documents import Document

from app.ingestion.cleaning.base import DocumentCleaner


class HyphenationFixer(DocumentCleaner):
    """
    Rejoins words split across a line break with a hyphen, e.g.
    "informa-\\ntion" -> "information". Common artifact from PDF
    text extraction and OCR line-wrapping.
    """
    _HYPHEN_BREAK = re.compile(r"(\w+)-\n(\w+)")

    def clean(self, document: Document) -> Document:
        text = self._HYPHEN_BREAK.sub(r"\1\2", document.page_content)
        return Document(page_content=text, metadata=document.metadata)


class HeaderFooterStripper(DocumentCleaner):
    """
    Strips lines that look like page numbers or "Page X of Y".
    Single-page heuristic (doesn't compare across pages) — for
    running titles/footers that repeat verbatim across many pages,
    see RepeatedLineDeduplicator in deduplication.py instead.
    """
    _PAGE_NUMBER = re.compile(r"^\s*(page\s+)?\d+(\s*/\s*\d+)?\s*$", re.IGNORECASE)
    _PAGE_OF = re.compile(r"^\s*page\s+\d+\s+of\s+\d+\s*$", re.IGNORECASE)

    def clean(self, document: Document) -> Document:
        lines = document.page_content.split("\n")
        kept = [
            line for line in lines
            if not self._PAGE_NUMBER.match(line) and not self._PAGE_OF.match(line)
        ]
        return Document(page_content="\n".join(kept), metadata=document.metadata)


class BulletNormalizer(DocumentCleaner):
    """
    Normalizes different bullet glyphs (•, ●, ▪, *) to a consistent
    "- " prefix, so downstream chunking/parsing sees uniform lists
    regardless of source format (PPTX bullets vs. PDF bullets differ).
    """
    _BULLET = re.compile(r"^[\u2022\u25cf\u25aa\*]\s*", re.MULTILINE)

    def clean(self, document: Document) -> Document:
        text = self._BULLET.sub("- ", document.page_content)
        return Document(page_content=text, metadata=document.metadata)