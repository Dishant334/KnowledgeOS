# app/db/models/document_blob.py
from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class DocumentBlob(Base):
    __tablename__ = "document_blobs"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)  # document_id/hash
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)