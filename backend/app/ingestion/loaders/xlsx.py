# app/ingestion/loaders/xlsx.py

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import UnstructuredExcelLoader

from app.ingestion.loaders.base import BaseLoader


class XLSXLoader(BaseLoader):

    async def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:

        if not data:
            raise ValueError("XLSX data is empty")

        metadata = metadata or {}

        temp_path: Path | None = None

        try:
            with NamedTemporaryFile(
                suffix=".xlsx",
                delete=False,
            ) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            loader = UnstructuredExcelLoader(
                str(temp_path),
                mode="elements",
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
                            "file_type": "xlsx",
                            **document.metadata,
                        },
                    }
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()