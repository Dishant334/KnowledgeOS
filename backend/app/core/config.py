from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
     database_url: str
     clerk_publishable_key: str
     clerk_secret_key: str
     clerk_jwks_url: str          # https://<your-domain>.clerk.accounts.dev/.well-known/jwks.json
     clerk_issuer: str            # https://<your-domain>.clerk.accounts.dev
     clerk_webhook_secret: str    # for verifying Clerk → backend webhooks
     qdrant_url: str

     model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings=Settings()
