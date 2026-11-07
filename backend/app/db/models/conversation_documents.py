from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ConversationDocument(Base):
    """A document attached to a conversation. Questions in that conversation search only its documents."""

    __tablename__ = "conversation_documents"

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

    # True when the upload made in this chat created the document (not just attached an existing one).
    # Only such documents are deleted with the chat when it is abandoned without a message.
    uploaded_here: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, server_default=func.now())
