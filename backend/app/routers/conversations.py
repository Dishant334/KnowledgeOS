from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.database import SessionLocal, get_db
from app.db.models.conversation import Conversation
from app.db.models.user import User
from app.dependencies.auth import get_current_user
from app.generation.llm import get_llm
from app.services.conversation_memory import has_something_to_remember, remember_conversation
from app.schemas.conversation import ConversationCreate, ConversationDetailOut, ConversationOut, ConversationRename
from app.schemas.document import DocumentOut
from app.services.conversations import (
    create_conversation,
    delete_conversation,
    discard_empty_conversation,
    find_user_conversation,
    get_conversation,
    list_conversation_documents,
    list_conversations,
    rename_conversation,
    sweep_abandoned_conversations,
)

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=list[ConversationOut])
def conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Your conversations that have messages, most recently active first (for a sidebar)."""
    sweep_abandoned_conversations(db, current_user)    # tidy up empty chats left behind (closed tab, crash)
    return list_conversations(db, user_id=current_user.id, limit=limit, offset=offset)


@router.get("/{conversation_id}", response_model=ConversationDetailOut)
def conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The whole conversation in one request: every message, and for each answer the sources it cited."""
    try:
        return get_conversation(db, user_id=current_user.id, conversation_id=conversation_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def new_conversation(
    body: ConversationCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start a new, empty chat. Attach documents by uploading with this id, then pass /ask the id to ask into it.
    It is not listed until it has a message, and is removed (with the files uploaded only into it) if abandoned.
    """
    sweep_abandoned_conversations(db, current_user)
    return create_conversation(db, user_id=current_user.id, title=body.title if body else None)


@router.patch("/{conversation_id}", response_model=ConversationOut)
def rename(
    conversation_id: UUID,
    body: ConversationRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change a conversation's title."""
    try:
        return rename_conversation(db, user_id=current_user.id, conversation_id=conversation_id, title=body.title)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation with its messages and saved citations (documents and long-term memory stay)."""
    try:
        delete_conversation(db, user_id=current_user.id, conversation_id=conversation_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/documents", response_model=list[DocumentOut])
def conversation_documents(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The documents attached to this conversation (its questions search only these)."""
    try:
        return list_conversation_documents(db, user_id=current_user.id, conversation_id=conversation_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{conversation_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
def discard(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove a chat you left WITHOUT asking anything, together with the files uploaded only into it.
    409 (and nothing deleted) if the chat has any message.
    """
    try:
        discard_empty_conversation(db, current_user, conversation_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _remember_in_background(user_id: int, conversation_pk: int, llm) -> None:
    """Runs after the response was sent, with its own database session (the request's one is closed by then)."""
    with SessionLocal() as db:
        conversation = db.get(Conversation, conversation_pk)   # the internal id
        if conversation is not None and conversation.user_id == user_id:
            remember_conversation(db, user_id, conversation, llm)


@router.post("/{conversation_id}/remember", status_code=status.HTTP_202_ACCEPTED)
def remember(
    conversation_id: UUID,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm=Depends(get_llm),
):
    """
    "I am leaving this chat": learn what matters about you from its new messages (one LLM call, in the background)
    and merge it into your long-term memory. Nothing to learn -> {"queued": false} and no LLM call.
    """
    try:
        conversation = find_user_conversation(db, current_user.id, conversation_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not has_something_to_remember(db, conversation):
        return {"queued": False}
    background.add_task(_remember_in_background, current_user.id, conversation.id, llm)
    return {"queued": True}
