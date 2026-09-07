# app/augmentation/models.py

from dataclasses import dataclass, field


@dataclass
class Citation:
    marker: str            # "[1]", "[2]", etc.
    document_id: str
    source_name: str
    page_number: int | None = None
    slide_number: int | None = None
    section_title: str | None = None


@dataclass
class AugmentedContext:
    prompt_context: str            # the assembled context block, ready to insert into the prompt
    citations: list[Citation] = field(default_factory=list)
    chunks_used: int = 0
    chunks_dropped: int = 0        # how many candidates got cut for token budget