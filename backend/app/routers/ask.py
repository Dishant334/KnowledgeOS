from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.db.database import get_db
from app.db.models.user import User
from app.schemas.ask import AskRequest, AskResponse
from app.services.ask import ask_question

router = APIRouter()


@router.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return ask_question(db, user_id=current_user.id, request=request)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))