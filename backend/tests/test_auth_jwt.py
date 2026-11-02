"""Clerk JWT verification + get_current_user + protected-route enforcement."""

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models.user import User
from tests.conftest import (
    OTHER_PRIVATE_KEY,
    PUBLIC_KEY,
    TEST_KID,
    auth_header,
    make_token,
    unique_clerk_id,
)

ME = "/users/me"


def _provision(db, clerk_user_id: str, email: str | None = "alice@example.com") -> User:
    user = User(clerk_user_id=clerk_user_id, email=email, name="Alice")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Missing / malformed credentials --------------------------------------


def test_no_token_401(client):
    assert client.get(ME).status_code == 401


def test_non_bearer_scheme_401(client):
    assert client.get(ME, headers={"Authorization": "Basic dXNlcjpwYXNz"}).status_code == 401


def test_garbage_token_401(client):
    assert client.get(ME, headers=auth_header("not-a-jwt")).status_code == 401


# --- Claim / signature enforcement ----------------------------------------


def test_expired_token_401(client, db):
    sub = unique_clerk_id()
    _provision(db, sub)
    assert client.get(ME, headers=auth_header(make_token(sub, exp_in=-60))).status_code == 401


def test_not_yet_valid_token_401(client, db):
    sub = unique_clerk_id()
    _provision(db, sub)
    assert client.get(ME, headers=auth_header(make_token(sub, nbf_in=600))).status_code == 401


def test_wrong_issuer_401(client, db):
    sub = unique_clerk_id()
    _provision(db, sub)
    token = make_token(sub, issuer="https://evil.clerk.accounts.dev")
    assert client.get(ME, headers=auth_header(token)).status_code == 401


def test_missing_issuer_401(client, db):
    sub = unique_clerk_id()
    _provision(db, sub)
    assert client.get(ME, headers=auth_header(make_token(sub, issuer=None))).status_code == 401


def test_wrong_signature_401(client, db):
    """Signed by a different key but claiming the trusted kid."""
    sub = unique_clerk_id()
    _provision(db, sub)
    token = make_token(sub, key=OTHER_PRIVATE_KEY)
    assert client.get(ME, headers=auth_header(token)).status_code == 401


def test_unknown_kid_401(client, db):
    sub = unique_clerk_id()
    _provision(db, sub)
    token = make_token(sub, kid="rotated-away")
    assert client.get(ME, headers=auth_header(token)).status_code == 401


def test_hs256_algorithm_confusion_401(client, db):
    """Classic attack: HMAC-sign with the RSA *public* key as the secret."""
    sub = unique_clerk_id()
    _provision(db, sub)
    pem = PUBLIC_KEY.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    import hashlib
    import hmac
    import json
    import time

    def b64(b):
        return jwt.utils.base64url_encode(b).decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": TEST_KID}).encode())
    payload = b64(
        json.dumps(
            {"sub": sub, "iss": "https://test-instance.clerk.accounts.dev", "exp": int(time.time()) + 300}
        ).encode()
    )
    sig = b64(hmac.new(pem, f"{header}.{payload}".encode(), hashlib.sha256).digest())
    assert client.get(ME, headers=auth_header(f"{header}.{payload}.{sig}")).status_code == 401


def test_alg_none_401(client, db):
    sub = unique_clerk_id()
    _provision(db, sub)
    token = jwt.encode(
        {"sub": sub, "iss": "https://test-instance.clerk.accounts.dev"},
        key=None,
        algorithm="none",
        headers={"kid": TEST_KID},
    )
    assert client.get(ME, headers=auth_header(token)).status_code == 401


def test_token_without_exp_401(client, db):
    """A token with no expiry must not be accepted forever."""
    sub = unique_clerk_id()
    _provision(db, sub)
    assert client.get(ME, headers=auth_header(make_token(sub, exp_in=None))).status_code == 401


def test_token_without_sub_401(client):
    assert client.get(ME, headers=auth_header(make_token(sub=None))).status_code == 401


def test_unauthorized_party_rejected_when_configured(client, db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "clerk_authorized_parties", "http://localhost:5173")
    sub = unique_clerk_id()
    _provision(db, sub)
    bad = make_token(sub, azp="https://evil.example.com")
    good = make_token(sub, azp="http://localhost:5173")
    assert client.get(ME, headers=auth_header(bad)).status_code == 401
    assert client.get(ME, headers=auth_header(good)).status_code == 200


def test_jwks_unavailable_503(client, fake_jwks):
    """JWKS outage is a server problem, not the caller's fault."""
    fake_jwks.unavailable = True
    assert client.get(ME, headers=auth_header(make_token(unique_clerk_id()))).status_code == 503


# --- Identity mapping -------------------------------------------------------


def test_valid_token_provisioned_user_200(client, db):
    sub = unique_clerk_id()
    user = _provision(db, sub)
    resp = client.get(ME, headers=auth_header(make_token(sub)))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == user.id
    assert body["clerk_user_id"] == sub
    assert body["email"] == "alice@example.com"


def test_valid_token_user_with_null_email_200(client, db):
    sub = unique_clerk_id()
    _provision(db, sub, email=None)
    resp = client.get(ME, headers=auth_header(make_token(sub)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] is None


def test_valid_token_missing_local_user_is_provisioned(client, db):
    """Valid Clerk identity whose webhook hasn't arrived yet: create the local row."""
    sub = unique_clerk_id()
    resp = client.get(ME, headers=auth_header(make_token(sub)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["clerk_user_id"] == sub
    assert db.query(User).filter_by(clerk_user_id=sub).count() == 1


def test_repeated_requests_do_not_duplicate_user(client, db):
    sub = unique_clerk_id()
    token = make_token(sub)
    ids = {client.get(ME, headers=auth_header(token)).json()["id"] for _ in range(3)}
    assert len(ids) == 1
    assert db.query(User).filter_by(clerk_user_id=sub).count() == 1


# --- Route protection --------------------------------------------------------

PUBLIC_PATHS = {"/health", "/test-db", "/webhooks/clerk", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


def _operations(fastapi_app):
    """(method, path) for every documented operation.

    Uses the OpenAPI schema because FastAPI >=0.14x keeps included routers
    nested (app.routes is no longer a flat list of APIRoutes).
    """
    for path, item in fastapi_app.openapi()["paths"].items():
        for method in item:
            yield method.upper(), path


def _anonymous_call(client, method: str, path: str):
    return client.request(method, path.replace("{document_id}", "1"))


def test_auth_me_route_is_mounted(app):
    assert ("GET", ME) in set(_operations(app))
    assert ("POST", "/webhooks/clerk") in set(_operations(app))


def test_all_mounted_non_public_routes_require_auth(app, client):
    ops = [(m, p) for m, p in _operations(app) if p not in PUBLIC_PATHS]
    assert ops, "expected at least one protected route"
    for method, path in ops:
        assert _anonymous_call(client, method, path).status_code == 401, (method, path)


@pytest.mark.parametrize("module", ["app.routers.document", "app.routers.retrieve", "app.routers.ask"])
def test_feature_routers_require_auth(module):
    """Routers not yet mounted in main.py still declare auth on every route."""
    import importlib

    router = importlib.import_module(module).router
    test_app = FastAPI()
    test_app.include_router(router)
    c = TestClient(test_app)
    ops = list(_operations(test_app))
    assert ops
    for method, path in ops:
        assert _anonymous_call(c, method, path).status_code == 401, f"{module}: {method} {path}"


def test_concurrent_first_requests_create_one_user(db):
    """First-request provisioning racing itself (or a webhook) must not duplicate or error."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.db.database import SessionLocal
    from app.services.auth import get_or_create_user, upsert_user_from_clerk_event

    sub = unique_clerk_id()
    barrier = Barrier(8)

    def worker(i):
        session = SessionLocal()
        try:
            barrier.wait()
            if i % 2:
                return get_or_create_user(session, sub).id
            return upsert_user_from_clerk_event(session, sub, email="a@example.com", name="A").id
        finally:
            session.close()

    with ThreadPoolExecutor(8) as pool:
        ids = set(pool.map(worker, range(8)))

    assert len(ids) == 1
    assert db.query(User).filter_by(clerk_user_id=sub).count() == 1
