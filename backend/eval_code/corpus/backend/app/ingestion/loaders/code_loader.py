# CODEBASE-FEATURE (Stage 2): loader for ONE source code file.
from typing import Any

from langchain_core.documents import Document

from app.ingestion.codebase.policy import language_for
from app.ingestion.loaders.base import BaseLoader

# The one internal MIME type stored for every Tier 1 source file. Browsers send unreliable types for
# code (e.g. video/mp2t for .ts), so the upload service decides this from the file extension and the
# language comes from policy.language_for(filename), never from the MIME type.
CODE_MIME_TYPE = "text/x-code"


class CodeLoader(BaseLoader):
    """
    One Document for the whole file, with the text kept EXACTLY as written
    (tabs, CRLF, trailing spaces, blank lines): code is whitespace-sensitive,
    so nothing is stripped or normalised here.

    Decoding is strict UTF-8 (a BOM is dropped). We do NOT fall back to latin-1
    like the prose loader does: guessing the encoding of code silently produces
    garbage identifiers (policy S11), so a non-UTF-8 file is refused instead.
    """

    def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:
        language = language_for(filename)
        if language is None:
            raise ValueError(f"Unsupported code file: {filename}")

        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Source file is not valid UTF-8 text: {exc.reason}") from exc

        if not text.strip():
            raise ValueError("Code file is empty")

        return [
            Document(
                page_content=text,
                metadata={
                    **(metadata or {}),
                    "filename": filename,
                    "source": filename,
                    "file_path": filename,  # a zip (Stage 9) will carry the path inside the project
                    "language": language,
                    "file_type": "code",
                },
            )
        ]
