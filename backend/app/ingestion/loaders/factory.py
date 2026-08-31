# app/ingestion/loaders/factory.py

from app.ingestion.loaders.base import BaseLoader
from app.ingestion.loaders.pdf import PDFLoader
from app.ingestion.loaders.docx import DOCXLoader
from app.ingestion.loaders.csv import CSVFileLoader
from app.ingestion.loaders.html import HTMLLoader
from app.ingestion.loaders.xlsx import XLSXLoader
from app.ingestion.loaders.pptx import PPTXLoader


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

    else:
        raise ValueError(
            f"Unsupported MIME type: {mime_type}"
        )