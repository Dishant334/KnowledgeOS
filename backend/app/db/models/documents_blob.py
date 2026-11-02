# app/db/models/document_blob.py
from sqlalchemy import ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class DocumentBlob(Base):
    """
    Raw file bytes, one row per document, kept separate from `documents` so
    metadata queries never touch large payloads. Deleted automatically with
    its document (and therefore with its user) via ON DELETE CASCADE.
    """

    __tablename__ = "document_blobs"

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    document = relationship("Document", back_populates="blob")
