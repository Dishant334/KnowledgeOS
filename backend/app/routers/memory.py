from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.database import get_db

from app.db.models.user import User
from app.dependencies.auth import get_current_user
from app.schemas.memory import MemoryCreate, MemoryOut
from app.services.memory import (
    create_user_memory,
    delete_all_user_memories,
    delete_user_memory,
    list_user_memories,
)

router = APIRouter(prefix="/memory", tags=["Memory"])


@router.get("", response_model=list[MemoryOut])
def list_memories(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """What the assistant remembers about you across all conversations."""
    return list_user_memories(current_user.id, db)


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
def add_memory(body: MemoryCreate, current_user: User = Depends(get_current_user)):
    """Tell the assistant something to remember (e.g. "I work in the Berlin office")."""
    return create_user_memory(current_user.id, body.text)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget_one(memory_id: str, current_user: User = Depends(get_current_user)):
    delete_user_memory(current_user.id, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def forget_everything(current_user: User = Depends(get_current_user)):
    delete_all_user_memories(current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
