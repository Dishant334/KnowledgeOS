# app/ingestion/cleaning/orchestrator.py

import logging
from typing import Optional

from langchain_core.documents import Document

from app.ingestion.cleaning.model import CleaningConfig
from app.ingestion.cleaning.normalize import (
    ControlCharacterStripper,
    UnicodeNormalizer,
    WhitespaceNormalizer,
)
from app.ingestion.cleaning.structural import (
    HyphenationFixer,
    HeaderFooterStripper,
    BulletNormalizer,
)
from app.ingestion.cleaning.deduplication import (
    RepeatedLineDeduplicator,
    ConsecutiveDuplicateRemover,
)
from app.ingestion.cleaning.quality import QualityFlagger, EmptyContentFilter

logger = logging.getLogger(__name__)


class CleaningOrchestrator:
    """
    Runs a document through the cleaning stages in sequence:

        ControlCharacterStripper
        UnicodeNormalizer
        WhitespaceNormalizer
        HyphenationFixer
        HeaderFooterStripper
        BulletNormalizer
        RepeatedLineDeduplicator   (stateful across pages of one source)
        ConsecutiveDuplicateRemover
        QualityFlagger
        EmptyContentFilter          (only stage that can drop a document)

    Mirrors OCROrchestrator: stages are built and owned internally
    from a CleaningConfig, rather than passed in as an arbitrary list.
    """

    def __init__(self, config: Optional[CleaningConfig] = None):
        self.config = config or CleaningConfig()

        self.control_char_stripper = ControlCharacterStripper()
        self.unicode_normalizer = UnicodeNormalizer()
        self.whitespace_normalizer = WhitespaceNormalizer()
        self.hyphenation_fixer = HyphenationFixer()
        self.header_footer_stripper = HeaderFooterStripper()
        self.bullet_normalizer = BulletNormalizer()
        self.repeated_line_deduplicator = RepeatedLineDeduplicator(
            min_occurrences_to_strip=self.config.dedup_min_occurrences,
            min_line_length=self.config.dedup_min_line_length,
        )
        self.consecutive_duplicate_remover = ConsecutiveDuplicateRemover()
        self.quality_flagger = QualityFlagger(
            min_alnum_ratio=self.config.min_alnum_ratio,
            short_content_threshold=self.config.short_content_threshold,
        )
        self.empty_content_filter = EmptyContentFilter(
            min_characters=self.config.min_characters,
        )

        # Order matters — see class docstring.
        self._stages = [
            self.control_char_stripper,
            self.unicode_normalizer,
            self.whitespace_normalizer,
            self.hyphenation_fixer,
            self.header_footer_stripper,
            self.bullet_normalizer,
            self.repeated_line_deduplicator,
            self.consecutive_duplicate_remover,
            self.quality_flagger,
            self.empty_content_filter,
        ]

    def process_document(self, document: Document) -> Optional[Document]:
        """
        Runs one document (typically one page/slide/sheet) through
        every cleaning stage. Returns None if a stage (currently only
        EmptyContentFilter) drops it.
        """
        current: Optional[Document] = document

        for stage in self._stages:
            try:
                current = stage.clean(current)
            except Exception as exc:
                raise RuntimeError(
                    f"Cleaning failed at stage '{stage.__class__.__name__}'"
                ) from exc

            if current is None:
                logger.debug(
                    "Document dropped at stage '%s' (source=%s)",
                    stage.__class__.__name__,
                    document.metadata.get("source"),
                )
                return None

        return current

    def process_batch(self, documents: list[Document]) -> list[Document]:
        """
        Runs the cleaning stages over all pages of ONE source, IN ORDER.
        Order matters: RepeatedLineDeduplicator is stateful across pages
        and relies on seeing them in sequence to detect running headers/
        footers. Dropped documents (EmptyContentFilter) are excluded.
        """
        results = []
        for document in documents:
            cleaned = self.process_document(document)
            if cleaned is not None:
                results.append(cleaned)
        return results