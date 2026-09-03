# app/ingestion/pipeline.py

import logging

from langchain_core.documents import Document

from app.ingestion.loaders.factory import get_loader
from app.ingestion.ocr.orchestrator import OCROrchestrator
from app.ingestion.cleaning.orchestrator import CleaningOrchestrator
from app.ingestion.chunking.orchestrator import ChunkingOrchestrator
from app.ingestion.embedding.orchestrator import EmbeddingOrchestrator
from app.ingestion.model import IngestionResult

logger = logging.getLogger(__name__)

# only PDFs go through OCR in this pipeline
OCR_ELIGIBLE_MIME_TYPES = {"application/pdf"}

# these get created once when the module loads, so we are not
# reloading the embedding model / reconnecting to qdrant every time
ocr_orchestrator = OCROrchestrator()
cleaning_orchestrator = CleaningOrchestrator()
chunking_orchestrator = ChunkingOrchestrator()
embedding_orchestrator = EmbeddingOrchestrator()


async def ingest_file(
    data: bytes,
    filename: str,
    mime_type: str,
    metadata: dict | None = None,
) -> IngestionResult:
    """
    Runs one file through the whole pipeline:
    load -> ocr (if pdf) -> clean -> chunk -> embed + index
    """

    warnings = []

    try:
        # step 1: load the file using the right loader
        loader = get_loader(mime_type)
        documents = await loader.load(data, filename, metadata)

        if not documents:
            return IngestionResult(
                filename=filename,
                success=False,
                error="loader returned nothing",
            )

        # step 2: run ocr only if it's a pdf
        if mime_type in OCR_ELIGIBLE_MIME_TYPES:
            documents, ocr_warnings = run_ocr_on_pages(documents, data)
            warnings.extend(ocr_warnings)

        # step 3: clean the documents
        cleaned_documents = cleaning_orchestrator.process_batch(documents)

        if not cleaned_documents:
            return IngestionResult(
                filename=filename,
                success=False,
                num_documents=len(documents),
                warnings=warnings + ["everything got dropped during cleaning"],
                error="nothing left after cleaning",
            )

        # step 4: chunk the documents
        chunks = chunking_orchestrator.chunk_batch(cleaned_documents, mime_type=mime_type)

        if not chunks:
            return IngestionResult(
                filename=filename,
                success=False,
                num_documents=len(cleaned_documents),
                warnings=warnings + ["no chunks were made"],
                error="chunking gave no output",
            )

        # step 5: embed and put into qdrant
        point_ids = embedding_orchestrator.embed_and_index(chunks)

        return IngestionResult(
            filename=filename,
            success=True,
            num_documents=len(cleaned_documents),
            num_chunks=len(chunks),
            point_ids=point_ids,
            warnings=warnings,
        )

    except Exception as e:
        logger.exception(f"ingestion failed for {filename}")
        return IngestionResult(
            filename=filename,
            success=False,
            warnings=warnings,
            error=str(e),
        )


async def ingest_files(files: list[tuple[bytes, str, str]], metadata: dict | None = None) -> list[IngestionResult]:
    """
    files is a list of (data, filename, mime_type)
    just loops and calls ingest_file one by one
    """
    results = []

    for data, filename, mime_type in files:
        result = await ingest_file(data, filename, mime_type, metadata)
        results.append(result)

    return results


def run_ocr_on_pages(documents: list[Document], pdf_data: bytes):
    """
    goes through every page and checks if ocr is needed
    (OCROrchestrator decides that internally)
    """
    warnings = []
    new_documents = []

    for document in documents:
        page_number = document.metadata.get("page_number", 1)

        result = ocr_orchestrator.process_page(
            pdf_data=pdf_data,
            page_number=page_number,
            extracted_text=document.page_content,
        )

        if result.used_ocr:
            new_metadata = dict(document.metadata)
            new_metadata["ocr_used"] = True
            new_metadata["ocr_confidence"] = result.confidence
            new_metadata["low_confidence"] = result.low_confidence

            document = Document(page_content=result.text, metadata=new_metadata)

            if result.warnings:
                for w in result.warnings:
                    warnings.append(f"page_{page_number}: {w}")

        new_documents.append(document)

    return new_documents, warnings