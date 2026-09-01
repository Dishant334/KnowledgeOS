# app/ingestion/loaders/pptx.py

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import UnstructuredPowerPointLoader

from app.ingestion.loaders.base import BaseLoader
from langchain_core.documents import Document


class PPTXLoader(BaseLoader):

    async def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:

        if not data:
            raise ValueError("PPTX data is empty")

        metadata = metadata or {}

        temp_path: Path | None = None

        try:
            with NamedTemporaryFile(
                suffix=".pptx",
                delete=False,
            ) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            loader = UnstructuredPowerPointLoader(
                str(temp_path),
            )

            documents = loader.load()

            result = []

            for document in documents:
                result.append(
                    {
                        "content": document.page_content,
                        "metadata": {
                            **metadata,
                            "filename": filename,
                            "file_type": "pptx",
                            **document.metadata,
                        },
                    }
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()