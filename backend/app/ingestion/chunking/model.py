# app/ingestion/chunking/model.py

from dataclasses import dataclass, field
from enum import StrEnum


class DocumentType(StrEnum):
    """Logical document categories used to select chunking strategies."""

    PROSE = "prose"
    SLIDES = "slides"
    TABULAR = "tabular"
    HTML = "html"
    CODE = "code"  # CODEBASE-FEATURE
    PROJECT = "project"  # CODEBASE-FEATURE: a zip of many files, each chunked by its own tier


@dataclass(frozen=True)
class ChunkingConfig:
    """
    Configuration for all ingestion chunking strategies.

    The same configuration object is passed to every strategy, while
    each strategy only consumes the fields relevant to it.
    """

    # General / recursive chunking
    encoding_name: str = "cl100k_base"

    chunk_size: int = 512
    chunk_overlap: int = 64

    # Slides
    slide_max_tokens: int = 1024

    # Tables
    rows_per_chunk: int = 20

    # Source code (CODEBASE-FEATURE): neighbouring small functions/statements are merged until a chunk reaches this size
    code_min_chunk_tokens: int = 128

    # HTML
    html_headers_to_split_on: tuple[tuple[str, str], ...] = field(
        default_factory=lambda: (
            ("h1", "Header 1"),
            ("h2", "Header 2"),
            ("h3", "Header 3"),
        )
    )

    def __post_init__(self) -> None:
        """Validate configuration early instead of failing during ingestion."""

        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be greater than 0")

        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                "chunk_overlap must be smaller than chunk_size"
            )

        if self.slide_max_tokens <= 0:
            raise ValueError("slide_max_tokens must be greater than 0")

        if self.code_min_chunk_tokens < 0:
            raise ValueError("code_min_chunk_tokens cannot be negative")

        if self.rows_per_chunk <= 0:
            raise ValueError("rows_per_chunk must be greater than 0")

        if not self.encoding_name.strip():
            raise ValueError("encoding_name cannot be empty")

        if not self.html_headers_to_split_on:
            raise ValueError(
                "html_headers_to_split_on cannot be empty"
            )