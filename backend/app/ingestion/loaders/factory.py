# app/ingestion/loaders/factory.py

from app.ingestion.loaders.base import BaseLoader
from app.ingestion.loaders.pdf import PDFLoader
from app.ingestion.loaders.docx import DOCXLoader
from app.ingestion.loaders.csv import CSVFileLoader
from app.ingestion.loaders.html import HTMLLoader
from app.ingestion.loaders.xlsx import XLSXLoader
from app.ingestion.loaders.pptx import PPTXLoader
from app.ingestion.loaders.text import TextLoader


SUPPORTED_MIME_TYPES = frozenset({
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "text/html",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/markdown",
})


def get_loader(mime_type: str) -> BaseLoader:

    if mime_type == "application/pdf":
        return PDFLoader()

    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return DOCXLoader()

    elif mime_type == "text/csv":
        return CSVFileLoader()

    elif mime_type == "text/html":
        return HTMLLoader()

    elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return XLSXLoader()

    elif mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        return PPTXLoader()

    elif mime_type == "text/plain":
        return TextLoader(file_type="txt")

    elif mime_type == "text/markdown":
        return TextLoader(file_type="md")

    else:
        raise ValueError(
            f"Unsupported MIME type: {mime_type}"
        )