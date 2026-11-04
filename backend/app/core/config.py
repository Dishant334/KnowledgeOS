import os

from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
     database_url: str
     clerk_jwks_url: str          # https://<your-domain>.clerk.accounts.dev/.well-known/jwks.json
     clerk_issuer: str            # https://<your-domain>.clerk.accounts.dev
     # Optional: empty disables the webhook endpoint (returns 503) instead of crashing startup.
     clerk_webhook_secret: str = ""
     # Optional comma-separated allow-list for the JWT `azp` claim (your frontend origins),
     # e.g. "http://localhost:5173,https://app.example.com". Empty = not enforced.
     clerk_authorized_parties: str = ""
     # Not used by backend code yet (kept for the frontend / Clerk Backend API).
     clerk_publishable_key: str = ""
     clerk_secret_key: str = ""
     qdrant_url: str
     qdrant_collection: str = "documents"
     # Celery broker + result backend (compose sets redis://redis:6379/0 for containers).
     redis_url: str = "redis://localhost:6379/0"
     # Where fastembed stores model weights. fastembed itself only reads the
     # process environment, so this is passed explicitly (relative = CWD).
     fastembed_cache_path: str | None = None

     # --- LLM (see app/generation/llm.py) ---
     # Providers: "gemini" (cloud, free tier, deployable) or "ollama" (local).
     # Empty llm_provider = no LLM configured (/ask answers 503).
     llm_provider: str = ""
     # Used automatically if the primary fails (quota, outage). Empty = no fallback.
     llm_fallback_provider: str = ""
     gemini_api_key: str = ""     # free key from Google AI Studio
     # Free-tier Gemini models are retired quickly (2.5-flash already returns 404 for new accounts).
     # List what your key can use with: google.genai Client(api_key=...).models.list()
     gemini_model: str = "gemini-3.5-flash"
     ollama_model: str = "qwen3:8b"
     ollama_base_url: str = "http://localhost:11434"

     # --- Tracing with LangSmith (opt-in; see export_tracing_environment below) ---
     # PRIVACY: when on, every traced question, retrieved passage and answer is uploaded to
     # LangSmith's cloud. Turn the hide_* switches on to upload only the shape of each step.
     langsmith_tracing: bool = False
     langsmith_api_key: str = ""
     langsmith_project: str = "knowledgeos"
     langsmith_endpoint: str = "https://api.smith.langchain.com"
     langsmith_hide_inputs: bool = False
     langsmith_hide_outputs: bool = False

     model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # .env is shared with docker-compose (POSTGRES_*) and libraries
        # (FASTEMBED_CACHE_PATH, ...); ignore keys that aren't Settings fields.
        extra="ignore",
    )


settings=Settings()


def export_tracing_environment(s: Settings) -> bool:
    """
    LangChain / LangSmith read their configuration from environment VARIABLES, but
    Settings only reads the .env FILE into itself. Without this step the LANGSMITH_*
    lines in .env are silently ignored and nothing is ever traced.

    Returns True if tracing is on. Tracing needs both the switch and an API key;
    otherwise it is explicitly turned off, so it never starts by accident.
    """
    if not (s.langsmith_tracing and s.langsmith_api_key):
        os.environ["LANGSMITH_TRACING"] = "false"
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key
    os.environ["LANGSMITH_ENDPOINT"] = s.langsmith_endpoint
    os.environ["LANGSMITH_PROJECT"] = s.langsmith_project
    os.environ["LANGSMITH_HIDE_INPUTS"] = str(s.langsmith_hide_inputs).lower()
    os.environ["LANGSMITH_HIDE_OUTPUTS"] = str(s.langsmith_hide_outputs).lower()
    return True


tracing_enabled = export_tracing_environment(settings)
