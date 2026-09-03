import base64
import logging

from app.worker.celery_app import celery_app
from app.ingestion.pipeline import ingest_file

logger = logging.getLogger(__name__)


@celery_app.task(
    name="ingest_file_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def ingest_file_task(
    self,
    data_b64: str,
    filename: str,
    mime_type: str,
    metadata: dict | None = None,
):
    try:
        data = base64.b64decode(data_b64)

        result = ingest_file(
            data,
            filename,
            mime_type,
            metadata,
        )

        if not result.success:
            logger.warning(
                f"ingestion failed for {filename}: {result.error}"
            )

        return {
            "filename": result.filename,
            "success": result.success,
            "num_documents": result.num_documents,
            "num_chunks": result.num_chunks,
            "point_ids": result.point_ids,
            "warnings": result.warnings,
            "error": result.error,
        }

    except Exception as exc:
        logger.exception(
            f"ingestion task crashed for {filename}"
        )
        raise self.retry(exc=exc)