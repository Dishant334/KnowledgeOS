from uuid import UUID
import logging

from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.documents import Document
from app.db.models.user import User
from app.core.postgres_storage import PostgresStorage
from app.ingestion.hashing import compute_document_hash
from app.ingestion.loaders.factory import SUPPORTED_MIME_TYPES
from app.ingestion.loaders.code_loader import CODE_MIME_TYPE  # CODEBASE-FEATURE
from app.ingestion.codebase.policy import classify as classify_codebase_file, language_for  # CODEBASE-FEATURE
from app.db.models.documents_blob import DocumentBlob
from app.worker.celery_app import celery_app
from app.ingestion.embedding.vector_store import delete_document_points

logger = logging.getLogger(__name__)

# Dispatched by name so the API process never imports the worker task module
# (which loads embedding models and connects to Qdrant).
INGEST_TASK_NAME = "ingest_file_task"
# Bounded publish retries so an unreachable broker can't hang an upload request.
_DISPATCH_RETRY_POLICY = {"max_retries": 3, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5}


# Exactly the types the ingestion pipeline has loaders for.
ALLOWED_MIME_TYPES = SUPPORTED_MIME_TYPES

# Common aliases clients send for supported types.
_MIME_ALIASES = {"text/x-markdown": "text/markdown", "application/csv": "text/csv"}

# Used when the client sends no type or a generic one.
_EXTENSION_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}
_GENERIC_MIME_TYPES = {None, "", "application/octet-stream"}


# CODEBASE-FEATURE: why a code upload is refused (the policy's skip reason -> a message a user can act on).
_CODE_REFUSALS = {
    "secret_file": "This file name looks like it holds secrets (keys, credentials, .env), so it was not accepted.",
    "ignored_file": "Minified, generated and lock files are not accepted. Upload the original source file.",
    "ignored_dir": "Files from build or dependency folders are not accepted.",
    "unsafe_path": "The file name is not valid.",
}


# CODEBASE-FEATURE (Stage 4, S12): which kinds of file each chat mode accepts. A code chat takes source code plus
# Markdown and text (a README); everything else is a document and belongs in a documents chat.
CODE_CHAT_MIME_TYPES = frozenset({CODE_MIME_TYPE, "text/markdown", "text/plain"})

_DOCS_CHAT_REFUSES_CODE = "This is a documents chat: source code files go in a codebase chat. Start a new chat and choose Codebase."
_CODE_CHAT_REFUSES_DOCUMENT = (
    "This is a codebase chat: add source code files (or Markdown or text), not documents such as PDF, Word, "
    "spreadsheets or web pages. Start a documents chat for those."
)


def mode_refusal(mode: str, mime_type: str | None) -> str | None:
    """Why a file of this type may not go into a chat of this mode (None = allowed). Enforced by the server."""
    if mode == "code" and mime_type not in CODE_CHAT_MIME_TYPES:
        return _CODE_CHAT_REFUSES_DOCUMENT
    if mode != "code" and mime_type == CODE_MIME_TYPE:
        return _DOCS_CHAT_REFUSES_CODE
    return None


def resolve_mime_type(content_type: str | None, filename: str) -> str | None:
    # CODEBASE-FEATURE: for source code the EXTENSION decides, whatever the client sent
    # (browsers label .ts as video/mp2t and .py as octet-stream or text/plain).
    if language_for(filename):
        return CODE_MIME_TYPE
    content_type = (content_type or "").split(";")[0].strip().lower() or None
    if content_type in _GENERIC_MIME_TYPES:
        suffix = filename[filename.rfind("."):].lower() if "." in filename else ""
        return _EXTENSION_MIME_TYPES.get(suffix)
    return _MIME_ALIASES.get(content_type, content_type)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB for version 1

# create document
async def create_document(
    db: Session,
    user: User,
    file: UploadFile,
    conversation_id: UUID | None = None,
) -> Document:
    """
    Saves an upload (or returns the user's existing copy of the same file) and, when conversation_id is given,
    attaches it to that conversation: questions asked there search only its documents. The conversation must be
    the user's own (404 otherwise), checked before the file is read.
    """
    from app.services.conversations import find_user_conversation, link_document

    conversation = None
    if conversation_id is not None:
        try:
            conversation = find_user_conversation(db, user.id, conversation_id)
        except LookupError:
            raise HTTPException(status_code=404, detail="Conversation not found")

    # CODEBASE-FEATURE (S12): the chat's mode decides which files it accepts. Checked twice: on the type of the
    # incoming file BEFORE its bytes are read, and on the type of the document actually being linked (an upload of
    # bytes the user already has links their EXISTING document, which keeps its own name and type).
    if conversation is not None and file.filename:
        incoming = resolve_mime_type(file.content_type, file.filename)
        refusal = mode_refusal(conversation.mode, incoming) if incoming in ALLOWED_MIME_TYPES else None
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)

    document, created = await _save_document(db, user, file)
    if conversation is not None:
        refusal = mode_refusal(conversation.mode, document.mime_type)
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)
        link_document(db, conversation.id, document.id, uploaded_here=created)   # links use the internal id
    return document


async def _save_document(db: Session, user: User, file: UploadFile) -> tuple[Document, bool]:
    """(document, created): created is False when the user's existing copy of the same file is returned."""

    
    #Check duplicate
  

    # Validate filename
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required",
        )

    # Validate MIME type (normalizing aliases / generic types)
    mime_type = resolve_mime_type(file.content_type, file.filename)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type",
        )

    # CODEBASE-FEATURE: code files get the policy's name checks (secrets, minified/generated) before we
    # even read the bytes. Scoped to code on purpose: a docs upload named credentials.txt stays allowed.
    if mime_type == CODE_MIME_TYPE:
        verdict = classify_codebase_file(file.filename)
        if not verdict.accepted:
            raise HTTPException(status_code=400, detail=_CODE_REFUSALS.get(verdict.skip_reason, "This file was not accepted."))

    # Read file
    content = await file.read()

    document_hash = compute_document_hash(content)
    # Dedup is per user: never return another user's document.
    existing = _find_user_document_by_hash(db, user.id, document_hash)
    if existing:
        return existing, False

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
        mime_type=mime_type,
        file_size=len(content),
        status="pending",
        document_hash=document_hash,
        storage_key=document_hash,
    )
    storage_backend = PostgresStorage(db)

    try:
        db.add(document)
        db.flush()                           # assigns document.id, still same transaction

        blob = DocumentBlob(document_id=document.id, data=content)
        db.add(blob)

        db.commit()                           # ✅ document + blob committed together, atomically
        db.refresh(document)
    except IntegrityError:
        # Concurrent upload of the same file by the same user won the race
        # on uq_documents_user_id_document_hash: return that document.
        db.rollback()
        existing = _find_user_document_by_hash(db, user.id, document_hash)
        if existing:
            return existing, False
        raise HTTPException(status_code=500, detail="Failed to save document")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save document")

    # Queue ingestion only AFTER commit, so the worker can always see the row.
    _dispatch_ingestion(db, document)
    return document, True


def _dispatch_ingestion(db: Session, document: Document) -> None:
    try:
        celery_app.send_task(
            INGEST_TASK_NAME,
            args=[document.id],
            retry=True,
            retry_policy=_DISPATCH_RETRY_POLICY,
        )
    except Exception as exc:
        # The upload itself succeeded; make the queueing failure visible
        # instead of leaving the document silently "pending".
        logger.exception("Failed to queue ingestion for document %s", document.id)
        document.status = "failed"
        document.error_message = f"Failed to queue ingestion: {type(exc).__name__}: {exc}"[:1000]
        db.commit()
        db.refresh(document)

def _find_user_document_by_hash(db: Session, user_id: int, document_hash: str) -> Document | None:
    return (
        db.query(Document)
        .filter(Document.user_id == user_id, Document.document_hash == document_hash)
        .first()
    )


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

# delete_user_document — the blob is removed by ON DELETE CASCADE
def delete_user_document(db: Session, user: User, document_id: int) -> None:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user.id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove vectors FIRST: if Qdrant is unreachable, keep the document so
    # nothing is orphaned and the client can retry the delete.
    try:
        delete_document_points(document.id)
    except Exception:
        logger.exception("Failed to delete vectors for document %s", document.id)
        raise HTTPException(status_code=503, detail="Could not remove document vectors; try again")

    db.delete(document)
    db.commit()