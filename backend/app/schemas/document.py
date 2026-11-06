# app/schemas/document.py

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, computed_field


# Why a document failed, in words a user can act on. The stored error_message is raw exception text
# (it can name internal hosts, ports or paths), so it is NEVER returned; only these messages are.
FAILURE_REASONS = (
    ("loader returned nothing", "The file appears to be empty or could not be read."),
    ("nothing left after cleaning", "No readable text was found in the file."),
    ("chunking gave no output", "No readable text was found in the file."),
    ("Failed after", "A temporary problem stopped processing this file. Please try uploading it again."),
    ("Failed to queue ingestion", "Processing could not be started. Please try uploading the file again."),
)
GENERIC_FAILURE = "Processing failed. Please try uploading the file again."


def friendly_failure_reason(status: str, error_message: str | None) -> str | None:
    """None unless the document failed (a retrying document may still carry an old error text)."""
    if status != "failed":
        return None
    text = error_message or ""
    for prefix, message in FAILURE_REASONS:
        if text.startswith(prefix):
            return message
    return GENERIC_FAILURE


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    file_size: int
    status: str
    created_at: datetime
    updated_at: datetime
    error_message: str | None = Field(default=None, exclude=True)    # read from the database row, never sent out

    @computed_field
    @property
    def failure_reason(self) -> str | None:
        """For a failed document: a friendly reason to show next to the red badge (else null)."""
        return friendly_failure_reason(self.status, self.error_message)

    model_config = ConfigDict(from_attributes=True)

