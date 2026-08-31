from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.models.documents import Document
from app.db.models.user import User
from app.core.postgres_storage import PostgresStorage
from app.ingestion.hashing import compute_document_hash
from app.db.models.documents_blob import DocumentBlob


ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB for version 1

# create document
async def create_document(
    db: Session,
    user: User,
    file: UploadFile,
) -> Document:

    
    #Check duplicate
  

    # Validate filename
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required",
        )

    # Validate MIME type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type",
        )

    # Read file
    content = await file.read()

    document_hash = compute_document_hash(content)
    existing = db.query(Document).filter(Document.document_hash == document_hash).first()
    if existing:
        return existing

    # Validate size
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File size exceeds 20 MB limit",
        )

    # Create database record
    document = Document(
        user_id=user.id,
        filename=file.filename,
        mime_type=file.content_type,
        file_size=len(content),
        status="pending",
        document_hash=document_hash,
        storage_key=document_hash,
    )
    storage_backend = PostgresStorage(db)

    try:
        db.add(document)
        db.flush()                           # assigns document.id, still same transaction

        blob = DocumentBlob(key=document.storage_key, data=content)
        db.add(blob)

        db.commit()                           # ✅ document + blob committed together, atomically
        db.refresh(document)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save document")

    return document

#get all documents
def get_user_documents(
    db: Session,
    user: User,
) -> list[Document]:

    documents = (
        db.query(Document)
        .filter(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
        .all()
    )

    return documents

#get single document
def get_user_document(
    db: Session,
    user: User,
    document_id: int,
) -> Document:

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id,
            Document.user_id == user.id,
        )
        .first()
    )

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return document

# delete_user_document — now actually deletes the blob too
def delete_user_document(db: Session, user: User, document_id: int) -> None:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user.id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    db.query(DocumentBlob).filter(DocumentBlob.key == document.storage_key).delete()
    db.delete(document)
    db.commit()