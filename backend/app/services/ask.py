from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.messages import Message
from app.schemas.ask import AskRequest, AskResponse
from app.schemas.retrieve import RetrieveRequest
from app.services.retrieve import retrieve_chunks


def _get_or_create_conversation(
    db: Session, user_id: int, conversation_id: int | None
) -> Conversation:
    if conversation_id is not None:
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

    conversation = Conversation(user_id=user_id, title=None)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def ask_question(db: Session, user_id: int, request: AskRequest) -> AskResponse:
    """
    Stub ask service.

    Persists the real conversation/message turn (this is genuine Phase 1
    infra, not RAG logic) and calls the retrieval stub so the full
    request path is wired end-to-end. The grounded-answer generation
    chain (LLM + citations) lands in Phase 4/5 -- for now this returns a
    placeholder answer with no citations.
    """
    conversation = _get_or_create_conversation(db, user_id, request.conversation_id)

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.query,
    )
    db.add(user_message)
    db.commit()

    # Wired for the real pipeline later; currently always returns no results.
    retrieve_chunks(RetrieveRequest(query=request.query), user_id=user_id)

    placeholder_answer = (
        "This is a stub response -- retrieval and generation aren't "
        "implemented yet."
    )

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=placeholder_answer,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return AskResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=placeholder_answer,
        citations=[],
        created_at=assistant_message.created_at,
    )