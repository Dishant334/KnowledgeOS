# app/ingestion/loaders/text.py

from typing import Any

from langchain_core.documents import Document

from app.ingestion.loaders.base import BaseLoader


class TextLoader(BaseLoader):
    """Plain text and Markdown: one Document for the whole file."""

    def __init__(self, file_type: str = "txt"):
        self.file_type = file_type

    def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:

        if not data:
            raise ValueError("Text data is empty")

        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")

        return [
            Document(
                page_content=text,
                metadata={
                    **(metadata or {}),
                    "filename": filename,
                    "source": filename,
                    "file_type": self.file_type,
                },
            )
        ]
