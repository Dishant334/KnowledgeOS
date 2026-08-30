# app/core/postgres_storage.py
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.orm import Session
from app.core.storage import StorageBackend
from app.db.models.documents_blob import DocumentBlob


class PostgresStorage(StorageBackend):
    """
    Stores raw file bytes directly in Postgres via a dedicated blob table,
    kept separate from `documents` so metadata queries never touch large payloads.
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    async def save(self, path: str, data: bytes) -> None:
        # `path` is used as the lookup key (e.g. the document_id)
        blob = DocumentBlob(key=path, data=data)
        self.db.add(blob)

    async def read(self, path: str) -> bytes:
        blob = self.db.execute(
            select(DocumentBlob).where(DocumentBlob.key == path)
        ).scalar_one_or_none()
        if blob is None:
            raise FileNotFoundError(f"No blob found for key {path}")
        return blob.data

    async def delete(self, path: str) -> None:
        self.db.execute(sql_delete(DocumentBlob).where(DocumentBlob.key == path))