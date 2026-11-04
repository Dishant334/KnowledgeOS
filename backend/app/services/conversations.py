from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.messages import Message
from app.schemas.conversation import ConversationDetailOut, ConversationOut, MessageOut


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
    The user's conversations, most recently active first (empty new chats included).

    "Recently active" is the time of the newest MESSAGE (or the creation time of a chat that has
    none yet): conversations.updated_at is not touched when a message is added, so it cannot be
    used for ordering.
    """
    last_active = func.coalesce(func.max(Message.created_at), Conversation.created_at)
    rows = (
        db.query(Conversation, last_active, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)    # outer: a new chat has no messages
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
    Deletes the conversation with its messages and their saved citations (the relationship cascades).
    Uploaded documents, their vectors and the user's long-term memory facts are NOT touched.
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
