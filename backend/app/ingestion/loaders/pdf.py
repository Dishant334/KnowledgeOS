from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import PyMuPDFLoader

from app.ingestion.loaders.base import BaseLoader


class PDFLoader(BaseLoader):

    async def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:

        if not data:
            raise ValueError("PDF data is empty")

        metadata = metadata or {}

        temp_path: Path | None = None

        try:
            with NamedTemporaryFile(
                suffix=".pdf",
                delete=False,
            ) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            loader = PyMuPDFLoader(str(temp_path))

            documents = loader.load()

            result = []

            for document in documents:

                result.append(
                    {
                        "content": document.page_content,
                        "metadata": {
                            **metadata,
                            "filename": filename,
                            "file_type": "pdf",
                            **document.metadata,
                        },
                    }
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()