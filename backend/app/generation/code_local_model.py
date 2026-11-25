# app/generation/code_local_model.py
#
# S7: the cloud fallback (Gemini) would receive the retrieved SOURCE CODE. In a code chat the app therefore uses
# the primary model only (locally: Ollama), unless CODE_ALLOW_CLOUD_FALLBACK=true. If the primary fails, the user
# gets the normal "model failed" error instead of their code silently going to a third party.

import logging
from functools import lru_cache

from app.core.config import settings
from app.generation.llm import build_llm, get_llm

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_primary_llm():
    """The primary provider alone (no fallback chain); None if it cannot be built."""
    if not settings.llm_provider:
        return None
    try:
        return build_llm(settings.llm_provider)
    except ValueError as error:
        logger.error("Primary LLM %r unavailable for code chats: %s", settings.llm_provider, error)
        return None


def llm_for_mode(llm, mode: str):
    """
    The model to use for this chat. Only the app's own shared model (get_llm()) is swapped, and only for a code chat
    while the cloud fallback is not allowed; any other object (a test fake, a model passed in on purpose) is kept.
    """
    if mode != "code" or settings.code_allow_cloud_fallback or llm is None or llm is not get_llm():
        return llm
    return get_primary_llm()
