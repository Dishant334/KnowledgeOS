import logging
from contextlib import contextmanager

from sqlalchemy import text

from app.db.database import SessionLocal, engine
from app.db.models.documents import Document
from app.ingestion.embedding.models import EmbeddingConfig
from app.ingestion.embedding.vector_store import delete_document_points
from app.worker.celery_app import celery_app
from app.ingestion.pipeline import ingest_file

logger = logging.getLogger(__name__)

# Document.status lifecycle: pending -> processing -> ready | failed
# (back to pending while a transient failure is being retried)
STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

# Exponential backoff for retries: 30s, 60s, 120s.
_RETRY_BASE_SECONDS = 30

# Matches Document.error_message column length.
_ERROR_MAX_LEN = 1000


def _truncate(message: str | None) -> str | None:
    if message is None:
        return None
    return message[:_ERROR_MAX_LEN]


# Short document type stored on every chunk (Qdrant KEYWORD index `doc_type`).
_DOC_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "text/html": "html",
    "text/plain": "txt",
    "text/markdown": "md",
}


def build_chunk_metadata(document: Document) -> dict:
    """
    Metadata attached to every chunk of this document (and therefore to every
    Qdrant point). IDs are strings because the payload indexes are KEYWORD.
    """
    return {
        "document_id": str(document.id),
        "uploaded_by": str(document.user_id),
        "doc_type": _DOC_TYPES.get(document.mime_type, "other"),
        "mime_type": document.mime_type,
        "source_name": document.filename,
        "document_hash": document.document_hash,
        "embedding_model": EmbeddingConfig.dense_model_name,
        # created_at is stored as naive UTC; RFC 3339 for Qdrant's DATETIME index.
        "created_at": document.created_at.replace(microsecond=0).isoformat() + "Z",
    }


def _set_status(db, document: Document, status: str, error: str | None = None) -> None:
    document.status = status
    document.error_message = _truncate(error)
    db.commit()


# Namespace for pg advisory locks taken by this task (key = (namespace, document_id)).
_LOCK_NAMESPACE = 7301


@contextmanager
def _document_lock(document_id: int):
    """
    Session-level Postgres advisory lock on a DEDICATED connection, held for
    the whole task run. Yields True if acquired. If the worker dies, the
    connection drops and Postgres releases the lock automatically.
    """
    conn = engine.connect()
    acquired = False
    try:
        acquired = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(:ns, :id)"),
                {"ns": _LOCK_NAMESPACE, "id": document_id},
            ).scalar()
        )
        conn.commit()  # don't sit "idle in transaction" while ingesting
        yield acquired
    finally:
        if acquired:
            conn.execute(
                text("SELECT pg_advisory_unlock(:ns, :id)"),
                {"ns": _LOCK_NAMESPACE, "id": document_id},
            )
            conn.commit()
        conn.close()


@celery_app.task(
    name="ingest_file_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    # Ack only after the task finishes, and requeue if the worker process
    # dies mid-task, so an interrupted ingestion is redelivered, not lost.
    acks_late=True,
    reject_on_worker_lost=True,
)
def ingest_file_task(self, document_id: int):
    """
    Ingests one stored document: reads its bytes from Postgres
    (document_blobs), runs the ingestion pipeline, and records the outcome
    on Document.status / Document.error_message.

    Duplicate-safe: only one execution per document at a time (advisory
    lock), and already-ready documents are not re-processed.
    """
    with _document_lock(document_id) as acquired:
        if not acquired:
            logger.info("ingest_file_task: document %s already being processed, skipping", document_id)
            return {"document_id": document_id, "skipped": "in_progress"}
        return _ingest(self, document_id)


def _ingest(task, document_id: int):
    self = task
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document is None or document.blob is None:
            # Deleted after the task was queued — nothing to do.
            logger.info("ingest_file_task: document %s not found, skipping", document_id)
            return {"document_id": document_id, "skipped": "not_found"}

        if document.status == STATUS_READY:
            logger.info("ingest_file_task: document %s already ready, skipping", document_id)
            return {"document_id": document_id, "skipped": "already_ready"}

        _set_status(db, document, STATUS_PROCESSING)

        try:
            result = ingest_file(
                document.blob.data,
                document.filename,
                document.mime_type,
                build_chunk_metadata(document),
            )
        except Exception as exc:
            # Only transient infrastructure errors reach here (content errors
            # come back as result.success=False). Retry with backoff; give up
            # and mark failed once retries are exhausted.
            db.rollback()
            error = f"{type(exc).__name__}: {exc}"
            attempt = self.request.retries + 1
            if self.request.retries < self.max_retries:
                countdown = _RETRY_BASE_SECONDS * (2 ** self.request.retries)
                logger.warning(
                    "ingestion of document %s failed (attempt %s/%s), retrying in %ss: %s",
                    document_id, attempt, self.max_retries + 1, countdown, error,
                )
                _set_status(db, document, STATUS_PENDING,
                            f"Retrying (attempt {attempt}/{self.max_retries + 1}): {error}")
                raise self.retry(exc=exc, countdown=countdown)

            logger.exception("ingestion of document %s failed after %s attempts", document_id, attempt)
            _set_status(db, document, STATUS_FAILED, f"Failed after {attempt} attempts: {error}")
            return {"document_id": document_id, "status": STATUS_FAILED, "success": False, "error": error}

        # The document may have been deleted while we were indexing: don't
        # leave its freshly written vectors behind.
        still_exists = db.execute(
            text("SELECT 1 FROM documents WHERE id = :id"), {"id": document_id}
        ).scalar()
        if not still_exists:
            logger.info("document %s deleted during ingestion; removing its vectors", document_id)
            delete_document_points(document_id)
            return {"document_id": document_id, "skipped": "deleted_during_ingestion"}

        if result.success:
            _set_status(db, document, STATUS_READY)
        else:
            logger.warning("ingestion failed for document %s: %s", document_id, result.error)
            _set_status(db, document, STATUS_FAILED, result.error or "ingestion failed")

        return {
            "document_id": document_id,
            "status": document.status,
            "success": result.success,
            "num_documents": result.num_documents,
            "num_chunks": result.num_chunks,
            "point_ids": result.point_ids,
            "warnings": result.warnings,
            "error": result.error,
        }
    finally:
        db.close()
