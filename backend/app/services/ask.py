import logging
from dataclasses import asdict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.messages import Message
from app.generation.orchestrator import generate_answer, trim_history
from app.schemas.ask import AskRequest, AskResponse, Citation
from app.services.retrieve import run_retrieval

logger = logging.getLogger(__name__)

# How many earlier messages (user + assistant) are used as conversation context
HISTORY_MESSAGES = 10


def looks_like_quota_error(error: Exception) -> bool:
    """
    True if an LLM error means "too many requests / free quota used up".
    Every provider SDK raises its own exception type, so we look at the text.
    """
    text = f"{type(error).__name__} {error}".lower()
    words = ("429", "quota", "rate limit", "rate_limit", "ratelimit", "resource_exhausted", "too many requests")
    return any(word in text for word in words)


def _get_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter_by(id=conversation_id, user_id=user_id)
        .first()
    )
    if conversation is None:
        # Also covers another user's conversation id -- treated as
        # not-found rather than leaking a 403, consistent with
        # user-level data isolation.
        raise LookupError("Conversation not found")
    return conversation


def _load_history(db: Session, conversation_id: int) -> list[tuple[str, str]]:
    """The last few messages of a conversation as (role, content), oldest first."""
    messages = (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.id.desc())
        .limit(HISTORY_MESSAGES)
        .all()
    )
    messages.reverse()
    history = [(message.role, message.content) for message in messages]
    return trim_history(history)  # long answers must not push the prompt past the model's window


def _history_as_text(history: list[tuple[str, str]]) -> str:
    """Plain text for the query rewriter prompt."""
    lines = []
    for role, content in history:
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def ask_question(db: Session, user_id: int, request: AskRequest, llm) -> AskResponse:
    """
    retrieve -> build cited context -> generate answer -> save the turn.

    Nothing is saved if retrieval or the LLM fails, so the client can simply retry.
    """
    conversation = None
    history = []
    if request.conversation_id is not None:
        conversation = _get_conversation(db, user_id, request.conversation_id)
        history = _load_history(db, conversation.id)

    retrieval = run_retrieval(
        request.query,
        user_id=user_id,
        llm=llm,
        history=_history_as_text(history),
    )

    try:
        generation = generate_answer(request.query, llm, retrieval.chunks, history)
    except Exception as error:
        logger.exception("LLM call failed")
        if looks_like_quota_error(error):
            raise HTTPException(
                status_code=429,
                detail="The AI service is busy or its free quota is used up. Please try again later.",
            )
        raise HTTPException(status_code=502, detail="The language model request failed, please try again")

    if conversation is None:
        conversation = Conversation(user_id=user_id, title=request.query[:80])
        db.add(conversation)
        db.flush()  # gives the conversation an id

    db.add(Message(conversation_id=conversation.id, role="user", content=request.query))
    assistant_message = Message(conversation_id=conversation.id, role="assistant", content=generation.answer)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return AskResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=generation.answer,
        citations=[Citation(**asdict(citation)) for citation in generation.citations],
        abstained=generation.abstained,
        created_at=assistant_message.created_at,
    )
