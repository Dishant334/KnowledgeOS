from datetime import datetime
from uuid import UUID
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.ask import Citation


# A conversation title: surrounding spaces are removed first, then it must be 1 to 255 characters
# (so "   " is rejected instead of being saved as an empty title).
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


# CODEBASE-FEATURE
Mode = Literal["docs", "code"]


class ConversationCreate(BaseModel):
    """Body of POST /conversations (the whole body is optional)."""

    title: Title | None = None       # without one, the first question becomes the title
    mode: Mode = "docs"              # fixed for the life of the chat: 'docs' (documents) or 'code' (source code)


class ConversationRename(BaseModel):
    title: Title


class ConversationOut(BaseModel):
    """One row of the conversation list (the sidebar). `id` is the conversation's public UUID."""

    id: UUID
    title: str | None
    created_at: datetime
    last_message_at: datetime        # when the newest message was written (the list is sorted by this)
    message_count: int
    mode: Mode = "docs"              # CODEBASE-FEATURE

    model_config = ConfigDict(from_attributes=True)


class MessageOut(BaseModel):
    id: int
    role: str                        # "user" or "assistant"
    content: str
    created_at: datetime
    # The sources the answer cited, [] for user messages, refusals and answers saved before
    # citations were stored. Each one matches a [1], [2]... marker in `content`.
    citations: list[Citation] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ConversationDetailOut(BaseModel):
    """A whole conversation: everything the chat screen needs in a single request."""

    id: UUID
    title: str | None
    created_at: datetime
    last_message_at: datetime
    messages: list[MessageOut]
    mode: Mode = "docs"              # CODEBASE-FEATURE
