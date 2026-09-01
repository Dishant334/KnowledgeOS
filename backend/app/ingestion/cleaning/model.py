# app/ingestion/cleaning/models.py

from dataclasses import dataclass


@dataclass
class CleaningConfig:
    """
    Central knobs for the cleaning pipeline. Passed to build_default_pipeline()
    so callers don't need to know which cleaner uses which parameter.
    """
    min_characters: int = 10           # EmptyContentFilter floor
    min_alnum_ratio: float = 0.4       # QualityFlagger noise threshold
    short_content_threshold: int = 40  # QualityFlagger "short_content" flag
    dedup_min_occurrences: int = 3     # RepeatedLineDeduplicator
    dedup_min_line_length: int = 8     # RepeatedLineDeduplicator