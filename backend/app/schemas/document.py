# app/schemas/document.py

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    file_size: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

