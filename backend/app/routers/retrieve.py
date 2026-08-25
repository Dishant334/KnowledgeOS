from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.db.models.user import User
from app.schemas.retrieve import RetrieveRequest, RetrieveResponse
from app.services.retrieve import retrieve_chunks

router = APIRouter()


@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(
    request: RetrieveRequest,
    current_user: User = Depends(get_current_user),
):
    return retrieve_chunks(request, user_id=current_user.id)