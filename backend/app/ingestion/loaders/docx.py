# app/ingestion/loaders/docx.py

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import Docx2txtLoader

from app.ingestion.loaders.base import BaseLoader
from langchain_core.documents import Document


class DOCXLoader(BaseLoader):

    async def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:

        if not data:
            raise ValueError("DOCX data is empty")

        metadata = metadata or {}

        temp_path: Path | None = None

        try:
            # LangChain's Docx2txtLoader expects a file path,
            # so write the PostgreSQL bytes to a temporary file.
            with NamedTemporaryFile(
                suffix=".docx",
                delete=False,
            ) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            loader = Docx2txtLoader(str(temp_path))

            documents = loader.load()

            result = []

            for document in documents:
                result.append(
                    {
                        "content": document.page_content,
                        "metadata": {
                            **metadata,
                            "filename": filename,
                            "file_type": "docx",
                            **document.metadata,
                        },
                    }
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()