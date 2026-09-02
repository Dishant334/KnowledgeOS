# app/ingestion/loaders/pptx.py

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_core.documents import Document

from app.ingestion.loaders.base import BaseLoader


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
            with NamedTemporaryFile(suffix=".pptx", delete=False) as temp_file:
                temp_file.write(data)
                temp_path = Path(temp_file.name)

            # mode="elements" gives one element per text block/bullet,
            # each tagged with its slide number in metadata["page_number"].
            # Grouped below into one Document per slide, since splitting
            # a slide's bullets apart loses their shared context.
            loader = UnstructuredPowerPointLoader(str(temp_path), mode="elements")
            elements = loader.load()

            slides_content: dict[int, list[str]] = {}
            slides_metadata: dict[int, dict] = {}

            for element in elements:
                slide_number = element.metadata.get("page_number", 1)
                slides_content.setdefault(slide_number, []).append(element.page_content)
                slides_metadata.setdefault(slide_number, element.metadata)

            total_slides = len(slides_content)

            result: list[Document] = []
            for slide_number in sorted(slides_content):
                content = "\n".join(slides_content[slide_number])
                result.append(
                    Document(
                        page_content=content,
                        metadata={
                            **metadata,
                            **slides_metadata[slide_number],
                            "filename": filename,
                            "source": filename,
                            "file_type": "pptx",
                            "slide_number": slide_number,
                            "total_slides": total_slides,
                        },
                    )
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()