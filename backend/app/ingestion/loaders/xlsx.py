# app/ingestion/loaders/xlsx.py

from io import BytesIO
from typing import Any

import pandas as pd
from langchain_core.documents import Document

from app.ingestion.loaders.base import BaseLoader


class XLSXLoader(BaseLoader):

    async def load(
        self,
        data: bytes,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Document]:

        if not data:
            raise ValueError("XLSX data is empty")

        metadata = metadata or {}

        try:
            sheets = pd.read_excel(
                BytesIO(data),
                sheet_name=None,   # None -> dict of {sheet_name: DataFrame}, all sheets
                dtype=str,
                engine="openpyxl",
            )
        except Exception as exc:
            raise ValueError("Failed to read XLSX data") from exc

        result: list[Document] = []

        for sheet_name, df in sheets.items():
            df = df.fillna("")

            for row_index, row in df.iterrows():
                row_text = "\n".join(
                    f"{col}: {value}"
                    for col, value in row.items()
                    if str(value).strip()
                )

                if not row_text.strip():
                    continue

                result.append(
                    Document(
                        page_content=row_text,
                        metadata={
                            **metadata,
                            "filename": filename,
                            "source": filename,
                            "file_type": "xlsx",
                            "sheet_name": sheet_name,
                            "row_index": int(row_index),
                        },
                    )
                )

        return result