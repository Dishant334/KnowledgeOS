"""
LLM provider selection (app/generation/llm.py).

- UNIT (no network): provider building, fallback chain order, misconfiguration,
  quota-error detection. Uses fake models for the failover behaviour.
- INTEGRATION, local: real Qwen3 8B through Ollama. Auto-skipped if Ollama or
  the model is not available.
- INTEGRATION, cloud: real Gemini free tier. OPT-IN only (uses your quota):
      RUN_GEMINI_TESTS=1 pytest tests/test_llm.py
  The key is read from backend/.env (GEMINI_API_KEY).
"""

import logging
import os

import httpx
import pytest
from dotenv import dotenv_values
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda, RunnableWithFallbacks

from app.core.config import settings
from app.generation import llm as llm_module
from app.generation.llm import build_llm, get_llm
from app.generation.orchestrator import generate_answer
from app.retrieval.model import ScoredChunk
from app.services.ask import looks_like_quota_error
from tests.conftest import BACKEND_DIR


@pytest.fixture
def configure(monkeypatch):
    """configure(primary, fallback, gemini_key=...) sets the LLM settings and clears the cache."""

    def apply(primary="", fallback="", gemini_key=""):
        monkeypatch.setattr(settings, "llm_provider", primary)
        monkeypatch.setattr(settings, "llm_fallback_provider", fallback)
        monkeypatch.setattr(settings, "gemini_api_key", gemini_key)
        get_llm.cache_clear()

    yield apply
    get_llm.cache_clear()


# --- unit: building models ------------------------------------------------------------


def test_no_provider_means_no_llm(configure):
    configure()
    assert get_llm() is None


def test_gemini_is_built_with_safe_settings(configure):
    configure("gemini", gemini_key="fake-key-for-test")
    model = get_llm()
    assert type(model).__name__ == "ChatGoogleGenerativeAI"
    assert "gemini-2.5-flash" in model.model
    assert model.temperature == 0
    assert 1 <= model.max_retries <= 2     # the library default is 6: too slow to reach the fallback
    assert model.timeout == 30
    assert model.thinking_budget == 0


def test_ollama_is_built_with_safe_settings(configure):
    configure("ollama")
    model = get_llm()
    assert type(model).__name__ == "ChatOllama"
    assert model.model == "qwen3:8b"
    assert model.temperature == 0
    assert model.num_ctx == 8192
    assert model.reasoning is False        # no <think> text in answers
    assert model.base_url == "http://localhost:11434"


def test_ollama_has_a_request_timeout_so_a_stuck_model_falls_back(configure):
    configure("ollama")
    model = get_llm()
    assert model._client._client.timeout.read == llm_module.OLLAMA_TIMEOUT_SECONDS == 60


def test_local_first_order_is_ollama_then_gemini(configure):
    """The default for development: local Qwen answers, Gemini only if it fails."""
    configure("ollama", "gemini", gemini_key="fake-key-for-test")
    chain = get_llm()
    assert isinstance(chain, RunnableWithFallbacks)
    assert type(chain.runnable).__name__ == "ChatOllama"
    assert [type(m).__name__ for m in chain.fallbacks] == ["ChatGoogleGenerativeAI"]


def test_local_first_without_gemini_key_uses_only_the_local_model(configure):
    configure("ollama", "gemini")          # fallback skipped: no key
    assert type(get_llm()).__name__ == "ChatOllama"


def test_deployed_setup_gemini_only(configure):
    configure("gemini", "", gemini_key="fake-key-for-test")
    assert type(get_llm()).__name__ == "ChatGoogleGenerativeAI"


def test_cloud_primary_with_local_fallback_builds_a_chain(configure):
    configure("gemini", "ollama", gemini_key="fake-key-for-test")
    chain = get_llm()
    assert isinstance(chain, RunnableWithFallbacks)
    assert type(chain.runnable).__name__ == "ChatGoogleGenerativeAI"
    assert [type(m).__name__ for m in chain.fallbacks] == ["ChatOllama"]


def test_gemini_without_key_is_skipped_and_logged(configure, caplog, monkeypatch):
    monkeypatch.setattr(logging.getLogger("app.generation.llm"), "disabled", False)  # alembic may have disabled it
    configure("gemini")
    with caplog.at_level(logging.ERROR, logger="app.generation.llm"):
        assert get_llm() is None
    assert any("GEMINI_API_KEY is not set" in r.message for r in caplog.records)


def test_misconfigured_primary_falls_back_to_the_working_provider(configure):
    configure("gemini", "ollama")          # no Gemini key
    model = get_llm()
    assert type(model).__name__ == "ChatOllama"   # used directly, not wrapped


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        build_llm("skynet")


# --- unit: failover behaviour (fake models) -------------------------------------------------


def fake_model(answer=None, error=None, calls=None):
    def run(prompt_value):
        if calls is not None:
            calls.append(answer or "error")
        if error:
            raise error
        return answer

    return RunnableLambda(run)


def build_with(monkeypatch, configure, models, order=("gemini", "ollama")):
    configure(*order)
    monkeypatch.setattr(llm_module, "build_llm", lambda name: models[name])
    get_llm.cache_clear()
    return get_llm()


def chunk(text):
    return ScoredChunk(document=Document(page_content=text, metadata={"document_id": "1", "source_name": "a.pdf"}))


def test_fallback_answers_when_primary_hits_quota(configure, monkeypatch):
    cloud = fake_model(error=RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"))
    local = fake_model(answer="Twenty days [1].")
    chain = build_with(monkeypatch, configure, {"gemini": cloud, "ollama": local})

    result = generate_answer("How many days?", chain, [chunk("Twenty days of vacation.")])

    assert result.answer == "Twenty days [1]."


def test_fallback_not_used_when_primary_works(configure, monkeypatch):
    calls = []
    cloud = fake_model(answer="From the cloud [1].", calls=calls)
    local = fake_model(answer="From the local model [1].", calls=calls)
    chain = build_with(monkeypatch, configure, {"gemini": cloud, "ollama": local})

    result = generate_answer("How many days?", chain, [chunk("Twenty days of vacation.")])

    assert result.answer == "From the cloud [1]."
    assert calls == ["From the cloud [1]."]


def test_gemini_answers_when_the_local_model_is_down(configure, monkeypatch):
    local = fake_model(error=ConnectionError("connection refused: ollama is not running"))
    cloud = fake_model(answer="From Gemini [1].")
    chain = build_with(monkeypatch, configure, {"ollama": local, "gemini": cloud}, order=("ollama", "gemini"))

    result = generate_answer("How many days?", chain, [chunk("Twenty days of vacation.")])

    assert result.answer == "From Gemini [1]."


def test_local_model_answers_first_and_gemini_is_not_called(configure, monkeypatch):
    calls = []
    local = fake_model(answer="From Qwen [1].", calls=calls)
    cloud = fake_model(answer="From Gemini [1].", calls=calls)
    chain = build_with(monkeypatch, configure, {"ollama": local, "gemini": cloud}, order=("ollama", "gemini"))

    result = generate_answer("How many days?", chain, [chunk("Twenty days of vacation.")])

    assert result.answer == "From Qwen [1]."
    assert calls == ["From Qwen [1]."]     # nothing was sent to the cloud


def test_error_surfaces_when_both_providers_fail(configure, monkeypatch):
    cloud = fake_model(error=RuntimeError("429 quota"))
    local = fake_model(error=ConnectionError("ollama not running"))
    chain = build_with(monkeypatch, configure, {"gemini": cloud, "ollama": local})

    with pytest.raises(Exception) as caught:
        generate_answer("How many days?", chain, [chunk("Twenty days of vacation.")])

    assert looks_like_quota_error(caught.value)   # the user gets a "try later" 429, not a 502


@pytest.mark.parametrize("error,expected", [
    (RuntimeError("429 RESOURCE_EXHAUSTED. You exceeded your current quota"), True),
    (RuntimeError("Rate limit reached for model"), True),
    (RuntimeError("Too Many Requests"), True),
    (type("RateLimitError", (Exception,), {})("slow down"), True),
    (RuntimeError("401 API key not valid"), False),
    (ConnectionError("connection refused"), False),
])
def test_quota_error_detection(error, expected):
    assert looks_like_quota_error(error) is expected


# --- integration: local Qwen via Ollama --------------------------------------------------------


def ollama_has_model() -> bool:
    try:
        tags = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).json()
    except Exception:
        return False
    return any(m["name"].startswith(settings.ollama_model.split(":")[0]) for m in tags.get("models", []))


needs_ollama = pytest.mark.skipif(not ollama_has_model(), reason="Ollama or the model is not available")


@needs_ollama
def test_real_qwen_answers_with_citation_and_no_thinking_text():
    model = build_llm("ollama")
    chunks = [chunk("Employees receive twenty days of paid vacation per year."),
              chunk("The cafeteria serves lunch between noon and two.")]

    result = generate_answer("How many vacation days do employees get?", model, chunks)

    assert "twenty" in result.answer.lower() or "20" in result.answer
    assert "[1]" in result.answer
    assert "<think>" not in result.answer
    assert result.abstained is False and result.citations[0].marker == "[1]"


@needs_ollama
def test_real_qwen_refuses_when_context_does_not_contain_the_answer():
    model = build_llm("ollama")
    chunks = [chunk("The cafeteria serves lunch between noon and two.")]

    result = generate_answer("What is the CEO's salary?", model, chunks)

    assert result.abstained is True
    assert result.citations == []


# --- integration: real Gemini free tier (opt-in) --------------------------------------------------


def gemini_key_from_env_file() -> str:
    return dotenv_values(BACKEND_DIR / ".env").get("GEMINI_API_KEY", "") or ""


needs_gemini = pytest.mark.skipif(
    os.environ.get("RUN_GEMINI_TESTS") != "1" or not gemini_key_from_env_file().strip()
    or gemini_key_from_env_file() == "your-gemini-api-key",
    reason="opt-in: set RUN_GEMINI_TESTS=1 and a real GEMINI_API_KEY in backend/.env",
)


@needs_gemini
def test_real_gemini_answers_with_citation(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", gemini_key_from_env_file())
    model = build_llm("gemini")
    chunks = [chunk("Employees receive twenty days of paid vacation per year.")]

    result = generate_answer("How many vacation days do employees get?", model, chunks)

    assert "twenty" in result.answer.lower() or "20" in result.answer
    assert "[1]" in result.answer


@needs_gemini
def test_real_gemini_refuses_when_context_does_not_contain_the_answer(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", gemini_key_from_env_file())
    model = build_llm("gemini")

    result = generate_answer("What is the CEO's salary?", model, [chunk("The cafeteria serves lunch at noon.")])

    assert result.abstained is True
