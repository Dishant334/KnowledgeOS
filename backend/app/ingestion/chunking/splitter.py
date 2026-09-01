# app/ingestion/chunking/registry.py

from app.ingestion.chunking.base import ChunkingStrategy
from app.ingestion.chunking.model import ChunkingConfig, DocumentType
from app.ingestion.chunking.strategies import (
    RecursiveCharacterStrategy,
    ParentChildStrategy,
    SlidePassthroughStrategy,
    TableChunkingStrategy,
    HTMLSpecificStrategy,
)

_MIME_TO_DOCUMENT_TYPE: dict[str, DocumentType] = {
    "application/pdf": DocumentType.PROSE,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocumentType.PROSE,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": DocumentType.SLIDES,
    "text/csv": DocumentType.TABULAR,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": DocumentType.TABULAR,
    "text/html": DocumentType.HTML,
}

_STRATEGY_BUILDERS = {
    DocumentType.PROSE: ParentChildStrategy,
    DocumentType.SLIDES: SlidePassthroughStrategy,
    DocumentType.TABULAR: TableChunkingStrategy,
    DocumentType.HTML: HTMLSpecificStrategy,
}


def get_document_type(mime_type: str) -> DocumentType:
    doc_type = _MIME_TO_DOCUMENT_TYPE.get(mime_type)
    if doc_type is None:
        raise ValueError(f"No DocumentType mapping for MIME type: {mime_type}")
    return doc_type


def get_strategy_for_mime_type(mime_type: str, config: ChunkingConfig) -> ChunkingStrategy:
    doc_type = get_document_type(mime_type)
    builder = _STRATEGY_BUILDERS.get(doc_type)
    if builder is None:
        # Shouldn't happen given _STRATEGY_BUILDERS covers every DocumentType,
        # but fail loudly rather than silently defaulting.
        raise ValueError(f"No strategy registered for DocumentType: {doc_type}")
    return builder(config)