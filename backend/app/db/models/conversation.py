import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    # The id the API and the URLs use (/chat/<uuid>): random, so it reveals nothing and cannot be guessed.
    # The integer `id` above stays internal (foreign keys).
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        index=True,
        nullable=False,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Rolling summary of the older part of the conversation. The messages
    # themselves are never deleted; once they are folded into the summary,
    # the prompt uses the summary instead of the raw text.
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Messages with id <= this value are already covered by `summary`
    # (a plain number, not a foreign key: it only marks a position).
    summarized_until_message_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Messages with id <= this value were already given to the long-term memory step
    # (services/conversation_memory.py), so they never cost a second LLM call.
    remembered_until_message_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="conversations",
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )