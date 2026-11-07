from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies.auth import get_current_user
from app.schemas.conversation import ConversationCreate, ConversationDetailOut, ConversationOut, ConversationRename
from app.schemas.document import DocumentOut
from app.services.conversations import (
    create_conversation,
    delete_conversation,
    discard_empty_conversation,
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
    conversation_id: int,
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
    conversation_id: int,
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
    conversation_id: int,
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
    conversation_id: int,
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
    conversation_id: int,
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
