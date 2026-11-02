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

     model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # .env is shared with docker-compose (POSTGRES_*) and libraries
        # (FASTEMBED_CACHE_PATH, ...); ignore keys that aren't Settings fields.
        extra="ignore",
    )


settings=Settings()
