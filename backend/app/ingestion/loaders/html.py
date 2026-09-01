# app/ingestion/loaders/html.py

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import BSHTMLLoader

from app.ingestion.loaders.base import BaseLoader
from langchain_core.documents import Document


class HTMLLoader(BaseLoader):

    async def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:

        if not data:
            raise ValueError("HTML data is empty")

        metadata = metadata or {}

        temp_path: Path | None = None

        try:
            with NamedTemporaryFile(
                suffix=".html",
                delete=False,
            ) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            loader = BSHTMLLoader(
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
                            "file_type": "html",
                            **document.metadata,
                        },
                    }
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()