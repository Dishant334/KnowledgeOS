# app/ingestion/loaders/base.py

from abc import ABC, abstractmethod
from typing import Any
from langchain_core.documents import Document


class BaseLoader(ABC):
    """
    Base interface for all document loaders.

    Supported loaders:
    - PDF
    - DOCX
    - CSV
    - HTML
    - XLSX
    - PPTX

    Synchronous by design: loaders do CPU/file work only and are called from
    the synchronous ingestion pipeline (Celery worker).
    """

    @abstractmethod
    def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:
        """
        Extract content from raw file bytes.

        Args:
            data: Raw file bytes (as stored in Postgres).
            filename: Original filename, used for metadata/citations.
            metadata: Extra metadata merged into every returned Document.

        Returns:
            A list of LangChain Documents (page_content + metadata), e.g. one
            per PDF page, slide, or spreadsheet row.

        Raises:
            ValueError: If the data is empty or the format is invalid.
            Exception: Loader-specific extraction errors.
        """
        raise NotImplementedError
