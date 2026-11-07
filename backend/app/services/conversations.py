import logging
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import exists, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from app.db.models.conversation import Conversation
from app.db.models.conversation_documents import ConversationDocument
from app.db.models.documents import Document
from app.db.models.messages import Message
from app.db.models.user import User
from app.schemas.conversation import ConversationDetailOut, ConversationOut, MessageOut

logger = logging.getLogger(__name__)

# An empty chat (no message at all) older than this is treated as abandoned and removed with the documents that
# were uploaded only into it. The frontend discards an empty chat at once when you leave it; this is the safety net
# for a closed tab or a crashed browser.
ABANDONED_AFTER = timedelta(hours=2)


def _find(db: Session, user_id: int, conversation_id: int) -> Conversation:
    """The user's own conversation, or LookupError (an unknown id and someone else's id look the same)."""
    conversation = db.query(Conversation).filter_by(id=conversation_id, user_id=user_id).first()
    if conversation is None:
        raise LookupError("Conversation not found")
    return conversation


def _row(db: Session, conversation: Conversation) -> ConversationOut:
    """The list-row view of one conversation (message count and time of the newest message)."""
    count, newest = db.query(func.count(Message.id), func.max(Message.created_at)).filter(
        Message.conversation_id == conversation.id
    ).one()
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        last_message_at=newest or conversation.created_at,
        message_count=count,
    )


def list_conversations(db: Session, user_id: int, limit: int = 50, offset: int = 0) -> list[ConversationOut]:
    """
    The user's conversations that have at least one message, most recently active first. An empty chat
    (created, maybe with documents uploaded, but never asked anything) is NOT listed.

    "Recently active" is the time of the newest MESSAGE: conversations.updated_at is not touched when a
    message is added, so it cannot be used for ordering.
    """
    last_active = func.max(Message.created_at)
    rows = (
        db.query(Conversation, last_active, func.count(Message.id))
        .join(Message, Message.conversation_id == Conversation.id)    # inner join: chats without messages drop out
        .filter(Conversation.user_id == user_id)
        .group_by(Conversation.id)
        .order_by(last_active.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        ConversationOut(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            last_message_at=newest,
            message_count=count,
        )
        for conversation, newest, count in rows
    ]


def create_conversation(db: Session, user_id: int, title: str | None = None) -> ConversationOut:
    """
    A new, empty chat ("New chat"). Without a title it stays untitled until the first question,
    which then becomes the title (see ask_stream); a title given here is never replaced.
    """
    conversation = Conversation(user_id=user_id, title=title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _row(db, conversation)


def rename_conversation(db: Session, user_id: int, conversation_id: int, title: str) -> ConversationOut:
    conversation = _find(db, user_id, conversation_id)
    conversation.title = title
    db.commit()
    db.refresh(conversation)
    return _row(db, conversation)


def delete_conversation(db: Session, user_id: int, conversation_id: int) -> None:
    """
    Deletes the conversation with its messages and their saved citations (the relationship cascades) and its
    document links (ON DELETE CASCADE). The documents themselves, their vectors and the user's long-term memory
    facts are NOT touched.
    """
    conversation = _find(db, user_id, conversation_id)
    db.delete(conversation)
    db.commit()


def get_conversation(db: Session, user_id: int, conversation_id: int) -> ConversationDetailOut:
    """
    One conversation with all its messages (oldest first), each answer carrying its citations.

    Raises LookupError if it does not exist OR belongs to someone else: both look the same to the
    caller, so ids of other users' conversations are never confirmed.
    """
    conversation = _find(db, user_id, conversation_id)

    messages = db.query(Message).filter_by(conversation_id=conversation.id).order_by(Message.id).all()
    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        last_message_at=messages[-1].created_at if messages else conversation.created_at,
        messages=[
            MessageOut(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                citations=message.citations or [],       # NULL (user message / older answer) -> []
            )
            for message in messages
        ],
    )


# --- documents attached to a conversation --------------------------------------------------------------------


def find_user_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation:
    """Public form of _find (LookupError for an unknown id or someone else's conversation)."""
    return _find(db, user_id, conversation_id)


def link_document(db: Session, conversation_id: int, document_id: int, uploaded_here: bool) -> None:
    """Attaches a document to a conversation (no error if it is already attached; the first link's flag is kept)."""
    db.execute(
        insert(ConversationDocument)
        .values(conversation_id=conversation_id, document_id=document_id, uploaded_here=uploaded_here)
        .on_conflict_do_nothing(index_elements=["conversation_id", "document_id"])
    )
    db.commit()


def conversation_document_ids(db: Session, conversation_id: int) -> list[int]:
    """Ids of the documents attached to a conversation (what its questions may search)."""
    rows = db.query(ConversationDocument.document_id).filter_by(conversation_id=conversation_id).all()
    return [document_id for (document_id,) in rows]


def list_conversation_documents(db: Session, user_id: int, conversation_id: int) -> list[Document]:
    """The user's conversation's documents, in the order they were attached (LookupError if not theirs)."""
    conversation = _find(db, user_id, conversation_id)
    return (
        db.query(Document)
        .join(ConversationDocument, ConversationDocument.document_id == Document.id)
        .filter(ConversationDocument.conversation_id == conversation.id, Document.user_id == user_id)
        .order_by(ConversationDocument.created_at, Document.id)
        .all()
    )


def _has_messages(db: Session, conversation_id: int) -> bool:
    return db.query(exists().where(Message.conversation_id == conversation_id)).scalar()


def _remove_empty(db: Session, user: User, conversation: Conversation) -> None:
    """
    Deletes an EMPTY conversation and the documents that were uploaded only into it: created by an upload in this
    chat (uploaded_here) and not attached to any other conversation. A document that was already in the library, or
    that another chat uses, stays. Vectors go first (delete_user_document), so a Qdrant outage leaves things retryable.
    """
    from app.services.document import delete_user_document  # local import: document.py imports this module

    other_link = aliased(ConversationDocument)        # a separate alias: the outer query also joins this table
    others = (
        exists()
        .where(other_link.document_id == Document.id, other_link.conversation_id != conversation.id)
        .correlate(Document)
    )
    own_ids = [
        document_id
        for (document_id,) in db.query(Document.id)
        .join(ConversationDocument, ConversationDocument.document_id == Document.id)
        .filter(
            ConversationDocument.conversation_id == conversation.id,
            ConversationDocument.uploaded_here.is_(True),
            Document.user_id == user.id,
            ~others,
        )
        .all()
    ]
    for document_id in own_ids:
        delete_user_document(db, user, document_id)
    db.delete(conversation)
    db.commit()


def discard_empty_conversation(db: Session, user: User, conversation_id: int) -> None:
    """
    "I left this chat without asking anything": removes it and its own documents. Refused (409) once the chat has a
    message, so a late call (for example from a closing tab just after a question) can never delete a real chat.
    """
    conversation = _find(db, user.id, conversation_id)
    if _has_messages(db, conversation.id):
        raise HTTPException(status_code=409, detail="This conversation has messages and was kept")
    _remove_empty(db, user, conversation)


def sweep_abandoned_conversations(db: Session, user: User, now: datetime | None = None) -> int:
    """Removes the user's empty conversations older than ABANDONED_AFTER. Never fails the caller; returns the count."""
    cutoff = (now or datetime.utcnow()) - ABANDONED_AFTER
    stale = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == user.id,
            Conversation.created_at < cutoff,
            ~exists().where(Message.conversation_id == Conversation.id),
        )
        .all()
    )
    removed = 0
    for conversation in stale:
        try:
            _remove_empty(db, user, conversation)
            removed += 1
        except Exception:
            db.rollback()
            logger.warning("Could not remove abandoned conversation %s; will retry later", conversation.id, exc_info=True)
    return removed
