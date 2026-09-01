# app/ingestion/cleaning/deduplication.py

import hashlib
from collections import defaultdict

from langchain_core.documents import Document

from app.ingestion.cleaning.base import DocumentCleaner


class RepeatedLineDeduplicator(DocumentCleaner):
    """
    Removes lines that repeat across multiple pages of the SAME
    source (e.g. a running header/footer HeaderFooterStripper's
    shape-based heuristic didn't catch).

    Stateful: tracks how many times each line has been seen per
    source across successive clean() calls. A line's first
    `min_occurrences_to_strip` appearances are kept (in case it's
    genuinely relevant on those pages); only once it's clearly
    repeating does it get stripped.

    Scope: this is WITHIN one source document, processed in page
    order via CleaningPipeline.run_batch(). It is NOT corpus-level
    near-duplicate detection across different documents — that's a
    separate concern (e.g. embedding similarity at index time) and
    deliberately out of scope here.
    """

    def __init__(self, min_occurrences_to_strip: int = 3, min_line_length: int = 8):
        self.min_occurrences_to_strip = min_occurrences_to_strip
        self.min_line_length = min_line_length
        self._seen: dict[str, dict[str, int]] = defaultdict(dict)

    def clean(self, document: Document) -> Document:
        source = document.metadata.get("source", "__unknown__")
        counts = self._seen[source]

        kept = []
        for line in document.page_content.split("\n"):
            stripped = line.strip()

            if len(stripped) < self.min_line_length:
                kept.append(line)  # too short to reliably judge as a repeat
                continue

            key = hashlib.sha1(stripped.lower().encode("utf-8")).hexdigest()
            counts[key] = counts.get(key, 0) + 1

            if counts[key] > self.min_occurrences_to_strip:
                continue  # seen on enough prior pages — drop it

            kept.append(line)

        return Document(page_content="\n".join(kept), metadata=document.metadata)


class ConsecutiveDuplicateRemover(DocumentCleaner):
    """
    Removes consecutive duplicate paragraphs within a SINGLE page —
    a common OCR artifact where overlapping OCR regions extract the
    same block of text twice in a row.
    """

    def clean(self, document: Document) -> Document:
        paragraphs = document.page_content.split("\n\n")
        deduped: list[str] = []
        for para in paragraphs:
            if deduped and para.strip() == deduped[-1].strip():
                continue
            deduped.append(para)
        return Document(page_content="\n\n".join(deduped), metadata=document.metadata)