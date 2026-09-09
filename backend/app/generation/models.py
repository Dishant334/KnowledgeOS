# app/generation/models.py

from dataclasses import dataclass, field
from app.augmentation.model import Citation


@dataclass
class GenerationResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    abstained: bool = False   # True if the model said "I don't know"