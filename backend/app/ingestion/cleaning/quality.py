# app/ingestion/cleaning/quality.py

from typing import Optional

from langchain_core.documents import Document

from app.ingestion.cleaning.base import DocumentCleaner


class QualityFlagger(DocumentCleaner):
    """
    Scores content quality and ATTACHES flags to metadata rather than
    dropping documents — downstream consumers (retrieval index,
    review queue) can decide what to do with flagged content instead
    of silently losing it.

    Sets document.metadata["quality_flags"] (a list), which may include:
      - "low_ocr_confidence": propagated from the OCR stage's
        `low_confidence` flag, if present on this document
      - "low_alnum_ratio": content is mostly non-alphanumeric noise
      - "short_content": content is short but above the hard drop
        floor enforced later by EmptyContentFilter
    """

    def __init__(self, min_alnum_ratio: float = 0.4, short_content_threshold: int = 40):
        self.min_alnum_ratio = min_alnum_ratio
        self.short_content_threshold = short_content_threshold

    def clean(self, document: Document) -> Document:
        text = document.page_content
        flags = list(document.metadata.get("quality_flags", []))

        if document.metadata.get("low_confidence"):
            flags.append("low_ocr_confidence")

        if text:
            alnum_ratio = sum(c.isalnum() for c in text) / len(text)
            if alnum_ratio < self.min_alnum_ratio:
                flags.append("low_alnum_ratio")

        if len(text.strip()) < self.short_content_threshold:
            flags.append("short_content")

        new_metadata = dict(document.metadata)
        new_metadata["quality_flags"] = flags
        return Document(page_content=text, metadata=new_metadata)


class EmptyContentFilter(DocumentCleaner):
    """
    Drops documents that are empty (or effectively empty) AFTER all
    prior cleaning steps have run. A page that was mostly headers/
    footers/repeated noise can end up with nothing left once those
    are stripped — no reason to carry it into chunking/embedding.

    Runs LAST in the pipeline: it must see final content, not
    pre-cleaning content, to avoid dropping pages that only look
    empty before normalization/dedup finish.
    """

    def __init__(self, min_characters: int = 10):
        self.min_characters = min_characters

    def clean(self, document: Document) -> Optional[Document]:
        if len(document.page_content.strip()) < self.min_characters:
            return None
        return document