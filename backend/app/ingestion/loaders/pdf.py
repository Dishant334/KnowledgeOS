from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from langchain_community.document_loaders import PyMuPDFLoader

from app.ingestion.loaders.base import BaseLoader
from langchain_core.documents import Document


class PDFLoader(BaseLoader):

    async def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:

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

            total_pages=len(documents)
            

            result = []

            for page_number,document in enumerate(documents, start=1):

                result.append(
                    Document({
                        "content": document.page_content,
                        "metadata": {
                            **metadata,
                            **document.metadata,
                            "filename": filename,
                            "source": filename,
                            "file_type": "pdf",
                              "page_number": page_number,
                            "total_pages": total_pages,
                            
                        },
                    })
                )

            return result

        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()