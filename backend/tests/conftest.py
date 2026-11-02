"""
Test harness for auth.

- Uses an isolated Postgres database (`<dev_db>_test`) on the same server as
  DATABASE_URL from backend/.env. The dev database is never touched.
- Clerk is fully mocked: tokens are signed with a locally generated RSA key and
  `app.core.clerk._jwk_client` is replaced with a fake JWKS client.
- Webhooks are signed with svix using a throwaway test secret.

Env vars MUST be set before any `app.*` import, because Settings and the
SQLAlchemy engine are created at import time.
"""

import base64
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from dotenv import dotenv_values

BACKEND_DIR = Path(__file__).resolve().parents[1]

TEST_ISSUER = "https://test-instance.clerk.accounts.dev"
TEST_JWKS_URL = f"{TEST_ISSUER}/.well-known/jwks.json"
TEST_KID = "test-kid"
TEST_QDRANT_COLLECTION = "knowledgeos_test_chunks"
TEST_WEBHOOK_SECRET = "whsec_" + base64.b64encode(secrets.token_bytes(24)).decode()


def _test_database_url() -> str:
    dev_url = os.environ.get("DATABASE_URL") or dotenv_values(BACKEND_DIR / ".env").get("DATABASE_URL")
    if not dev_url:
        raise RuntimeError("DATABASE_URL not found in environment or backend/.env")
    parsed = urlparse(dev_url)
    dev_db = parsed.path.lstrip("/")
    test_db = dev_db if dev_db.endswith("_test") else f"{dev_db}_test"
    return urlunparse(parsed._replace(path=f"/{test_db}"))


TEST_DATABASE_URL = _test_database_url()

os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL,
        "CLERK_JWKS_URL": TEST_JWKS_URL,
        "CLERK_ISSUER": TEST_ISSUER,
        "CLERK_WEBHOOK_SECRET": TEST_WEBHOOK_SECRET,
        "CLERK_SECRET_KEY": "sk_test_dummy",
        "CLERK_PUBLISHABLE_KEY": "pk_test_dummy",
        "QDRANT_URL": "http://localhost:6333",
        # Isolated Redis DB for tests; the dev queue lives on DB 0.
        "REDIS_URL": "redis://localhost:6379/15",
        # Separate Qdrant collection for tests; the app uses "documents".
        "QDRANT_COLLECTION": TEST_QDRANT_COLLECTION,
    }
)


def _ensure_test_database() -> None:
    parsed = urlparse(TEST_DATABASE_URL)
    test_db = parsed.path.lstrip("/")
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{test_db}"')


def _migrate_test_database() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


_ensure_test_database()
_migrate_test_database()


# ---------------------------------------------------------------------------
# RSA keys + fake JWKS client
# ---------------------------------------------------------------------------

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_KEY = PRIVATE_KEY.public_key()
OTHER_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _SigningKey:
    def __init__(self, key):
        self.key = key


class FakeJWKClient:
    """Mimics PyJWKClient.get_signing_key_from_jwt: resolves by `kid` header."""

    def __init__(self):
        self.keys = {TEST_KID: PUBLIC_KEY}
        self.unavailable = False

    def get_signing_key_from_jwt(self, token: str):
        if self.unavailable:
            raise jwt.PyJWKClientConnectionError("Fail to fetch data from the url")
        kid = jwt.get_unverified_header(token).get("kid")
        if kid not in self.keys:
            raise jwt.PyJWKClientError(f'Unable to find a signing key that matches: "{kid}"')
        return _SigningKey(self.keys[kid])


@pytest.fixture(autouse=True)
def fake_jwks(monkeypatch):
    import app.core.clerk as clerk

    fake = FakeJWKClient()
    monkeypatch.setattr(clerk, "_jwk_client", fake)
    return fake


def make_token(
    sub: str | None = "user_test_123",
    *,
    issuer: str | None = TEST_ISSUER,
    exp_in: int | None = 300,
    nbf_in: int | None = -5,
    key=None,
    kid: str = TEST_KID,
    algorithm: str = "RS256",
    **extra_claims,
) -> str:
    now = int(time.time())
    claims = {"iat": now - 5, "sid": "sess_test", **extra_claims}
    if sub is not None:
        claims["sub"] = sub
    if issuer is not None:
        claims["iss"] = issuer
    if exp_in is not None:
        claims["exp"] = now + exp_in
    if nbf_in is not None:
        claims["nbf"] = now + nbf_in
    return jwt.encode(claims, key or PRIVATE_KEY, algorithm=algorithm, headers={"kid": kid})


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# App, client, DB
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app

    return fastapi_app


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    # No `with` block: skip lifespan (it creates the chat-history table,
    # unrelated to auth).
    return TestClient(app)


@pytest.fixture
def db():
    from app.db.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    from sqlalchemy import text

    from app.db.database import engine

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users RESTART IDENTITY CASCADE"))


def unique_clerk_id() -> str:
    return f"user_{uuid.uuid4().hex[:16]}"


@pytest.fixture(scope="session", autouse=True)
def _drop_test_qdrant_collection():
    """Delete ONLY the test collection after the session (never "documents")."""
    yield
    assert TEST_QDRANT_COLLECTION != "documents"
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=os.environ["QDRANT_URL"])
        if client.collection_exists(TEST_QDRANT_COLLECTION):
            client.delete_collection(TEST_QDRANT_COLLECTION)
    except Exception:
        pass
