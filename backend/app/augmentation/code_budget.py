# app/augmentation/code_budget.py
#
# How much code may go into one prompt. Documents keep the 3,000-token budget (ContextBuilder's default);
# a code chat reads CODE_CONTEXT_TOKENS and CODE_TOP_K. Everything must fit Ollama's 8,192-token window:
# context + history (<=1,500) + summary (~250) + memory (<=500) + instructions and question (~400) + the answer.
# That is why CODE_CONTEXT_TOKENS is capped at 4,500 in the settings.

from functools import lru_cache

from app.augmentation.context_builder import ContextBuilder
from app.core.config import settings


@lru_cache(maxsize=1)
def get_code_context_builder() -> ContextBuilder:
    return ContextBuilder(max_context_tokens=settings.code_context_tokens)


def top_k_for(mode: str, default: int = 5) -> int:
    """How many chunks a question retrieves and sends: the usual 5 for documents, CODE_TOP_K for code."""
    return settings.code_top_k if mode == "code" else default
