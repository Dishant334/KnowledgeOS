# app/ingestion/loaders/base.py

from abc import ABC, abstractmethod
from pathlib import Path
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
    """

    @abstractmethod
    async def load(
        self,
        data:bytes,
    ) -> list[Document]:
        """
        Load and extract content from a file.

        Args:
            file_path: Path to the source file.

        Returns:
            A list of document units.

            Each unit should contain:
                {
                    "content": str,
                    "metadata": dict
                }

        Example:

            [
                {
                    "content": "Some extracted text...",
                    "metadata": {
                        "source": "document.pdf",
                        "file_type": "pdf",
                        "page_number": 1,
                    },
                }
            ]

        Raises:
            FileNotFoundError:
                If the file does not exist.

            ValueError:
                If the file format is unsupported or invalid.

            Exception:
                Loader-specific extraction errors.
        """
        pass