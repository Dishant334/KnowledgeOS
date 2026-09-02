# app/ingestion/loaders/html.py

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import BSHTMLLoader
from langchain_core.documents import Document

from app.ingestion.loaders.base import BaseLoader


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

        # Preserved BEFORE parsing, since BSHTMLLoader (BeautifulSoup)
        # extracts plain text and discards the original markup.
        # HTMLSpecificStrategy (chunking) needs this raw markup to
        # split on actual heading tags.
        raw_html = data.decode("utf-8", errors="replace")

        try:
            with NamedTemporaryFile(suffix=".html", delete=False) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            loader = BSHTMLLoader(str(temp_path))
            documents = loader.load()

            result: list[Document] = []
            for document in documents:
                result.append(
                    Document(
                        page_content=document.page_content,
                        metadata={
                            **metadata,
                            **document.metadata,
                            "filename": filename,
                            "source": filename,
                            "file_type": "html",
                            "raw_html": raw_html,
                        },
                    )
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()