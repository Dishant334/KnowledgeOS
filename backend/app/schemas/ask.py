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
    marker: str                       # "[1]" -- matches the marker used in the answer text
    document_id: Optional[int] = None
    source_name: Optional[str] = None
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    section_title: Optional[str] = None
    sheet_name: Optional[str] = None
    row_start: Optional[int] = None
    row_end: Optional[int] = None
    snippet: Optional[str] = None     # start of the cited passage, for the source card


class AskResponse(BaseModel):
    conversation_id: int
    message_id: int
    answer: str
    citations: list[Citation]
    abstained: bool = False           # True when the answer is "I don't have enough information"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)