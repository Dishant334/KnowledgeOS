from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    Response,
    status,
)

from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies.auth import get_current_user
from app.schemas.document import DocumentOut
from app.services.document import (
    create_document,
    get_user_documents,
    get_user_document,
    delete_user_document,
)


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return await create_document(
        db=db,
        user=current_user,
        file=file,
    )


@router.get(
    "",
    response_model=list[DocumentOut],
)
def get_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_documents(
        db=db,
        user=current_user,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
)
def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_user_document(
        db=db,
        user=current_user,
        document_id=document_id,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_user_document(
        db=db,
        user=current_user,
        document_id=document_id,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)