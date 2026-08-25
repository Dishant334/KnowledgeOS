from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    conversation_id: Optional[int] = Field(
        default=None,
        description="Omit to start a new conversation; pass an existing id to continue one.",
    )


class Citation(BaseModel):
    chunk_id: str
    document_id: int
    source_name: Optional[str] = None
    page_number: Optional[int] = None


class AskResponse(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    citations: list[Citation]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)