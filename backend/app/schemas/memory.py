from uuid import UUID
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=200, description="One short fact to remember about you.")


class MemoryOut(BaseModel):
    id: str
    text: str
    created_at: datetime
    source_conversation_id: Optional[UUID] = None  # public id of the chat it was learned from (None if added by hand)
