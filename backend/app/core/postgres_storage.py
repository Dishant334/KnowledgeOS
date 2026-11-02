# app/core/postgres_storage.py
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.orm import Session
from app.core.storage import StorageBackend
from app.db.models.documents_blob import DocumentBlob


class PostgresStorage(StorageBackend):
    """
    Stores raw file bytes directly in Postgres via a dedicated blob table,
    kept separate from `documents` so metadata queries never touch large payloads.

    `path` is the document id (as a string, to satisfy the StorageBackend
    interface). Blobs are one-per-document and removed by ON DELETE CASCADE
    when their document is deleted.
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    async def save(self, path: str, data: bytes) -> None:
        self.db.add(DocumentBlob(document_id=int(path), data=data))

    async def read(self, path: str) -> bytes:
        blob = self.db.execute(
            select(DocumentBlob).where(DocumentBlob.document_id == int(path))
        ).scalar_one_or_none()
        if blob is None:
            raise FileNotFoundError(f"No blob found for document {path}")
        return blob.data

    async def delete(self, path: str) -> None:
        self.db.execute(sql_delete(DocumentBlob).where(DocumentBlob.document_id == int(path)))
