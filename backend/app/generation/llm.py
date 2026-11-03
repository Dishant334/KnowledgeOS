# app/generation/llm.py

import logging
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("gemini", "ollama")

# How long we wait for the local model before giving up (the fallback then answers)
OLLAMA_TIMEOUT_SECONDS = 60


def build_llm(provider: str):
    """
    Builds one LangChain chat model.
    Raises ValueError if the provider is unknown or its settings are missing.

    - "ollama": a model running locally (default Qwen3 8B). Free, private and
      offline, but it only works where Ollama is installed and running.
      This is the primary on a development machine.
    - "gemini": Google's hosted model. The free tier costs nothing and works
      from any host, so it is the fallback locally and the primary when the
      app is deployed on a server without Ollama.
    """
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0,       # factual answers, not creative ones
            max_retries=2,       # keep this small (default is higher) so a quota error reaches the fallback quickly
            timeout=30,
            thinking_budget=0,   # no hidden "thinking" tokens (saves free quota; Flash models only)
        )

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            num_ctx=8192,        # Ollama's default window is smaller than our prompts
            reasoning=False,     # Qwen3 would otherwise add <think>...</think> text to answers
            client_kwargs={"timeout": OLLAMA_TIMEOUT_SECONDS},  # a stuck local model must fall back, not hang
        )

    raise ValueError(f"Unknown LLM provider {provider!r}; use one of {SUPPORTED_PROVIDERS}")


@lru_cache(maxsize=1)
def get_llm():
    """
    FastAPI dependency: the chat model used for query rewriting and answer
    generation. Built once, then reused.

    LLM_PROVIDER is tried first (locally: "ollama"); if it fails at request
    time (not running, timeout, quota used up) the LLM_FALLBACK_PROVIDER
    answers instead (locally: "gemini"). A provider that is misconfigured
    (e.g. missing key) is logged and skipped.

    Note: a fallback to a cloud provider sends the retrieved document text to
    that provider. Leave LLM_FALLBACK_PROVIDER empty to keep documents local.

    Returns None when no provider works: /ask then answers 503 and /retrieve
    skips query rewriting.
    """
    models = []
    for name in (settings.llm_provider, settings.llm_fallback_provider):
        if not name:
            continue
        try:
            models.append(build_llm(name))
            logger.info("LLM provider ready: %s", name)
        except ValueError as error:
            logger.error("LLM provider %r skipped: %s", name, error)

    if not models:
        return None

    return models[0].with_fallbacks(models[1:]) if len(models) > 1 else models[0]
