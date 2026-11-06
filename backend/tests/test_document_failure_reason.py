"""
A failed document shows the user WHY, but never the raw error text.

The stored error_message is exception text (it can contain internal hosts, ports and paths), so the API returns
a friendly `failure_reason` instead and leaves error_message out of every response.
"""

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.db.models import Document, DocumentBlob, User
from app.schemas.document import GENERIC_FAILURE, DocumentOut, friendly_failure_reason
from tests.conftest import auth_header, make_token, unique_clerk_id

RAW_INTERNAL = "Failed after 3 attempts: ConnectionError: Error 111 connecting to redis:6379 (10.0.0.5), /srv/app/secret.py"


def out(status, error_message=None) -> dict:
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(id=1, filename="a.pdf", mime_type="application/pdf", file_size=10, status=status,
                          error_message=error_message, created_at=now, updated_at=now)
    return DocumentOut.model_validate(row).model_dump(mode="json")


# --- the mapping ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("error, expected_fragment", [
    ("loader returned nothing", "empty or could not be read"),
    ("nothing left after cleaning", "No readable text"),
    ("chunking gave no output", "No readable text"),
    (RAW_INTERNAL, "temporary problem"),
    ("Failed to queue ingestion: OperationalError: connection to server at 10.0.0.5 failed", "could not be started"),
])
def test_known_failures_get_a_friendly_reason(error, expected_fragment):
    assert expected_fragment in friendly_failure_reason("failed", error)


def test_an_unknown_failure_gets_the_generic_reason():
    assert friendly_failure_reason("failed", "KeyError: 'weird internal thing'") == GENERIC_FAILURE
    assert friendly_failure_reason("failed", None) == GENERIC_FAILURE


@pytest.mark.parametrize("status", ["pending", "processing", "ready"])
def test_only_failed_documents_have_a_reason_even_if_an_old_error_is_still_stored(status):
    assert friendly_failure_reason(status, RAW_INTERNAL) is None       # a retrying document keeps its last error text


def test_the_response_has_the_reason_and_never_the_raw_error():
    body = out("failed", RAW_INTERNAL)

    assert "temporary problem" in body["failure_reason"]
    assert "error_message" not in body
    assert "10.0.0.5" not in str(body) and "redis" not in str(body) and "secret.py" not in str(body)
    assert out("ready")["failure_reason"] is None


# --- over HTTP -------------------------------------------------------------------------------------------


def make_document(db, user, status, error_message, name="a.pdf"):
    data = name.encode()
    digest = hashlib.sha256(data).hexdigest()
    doc = Document(user_id=user.id, filename=name, mime_type="application/pdf", file_size=len(data), status=status,
                   error_message=error_message, document_hash=digest, storage_key=digest)
    db.add(doc)
    db.flush()
    db.add(DocumentBlob(document_id=doc.id, data=data))
    db.commit()
    db.refresh(doc)
    return doc


def test_the_document_endpoints_return_the_reason_and_hide_the_raw_error(client, db):
    user = User(clerk_user_id=unique_clerk_id(), email="u@example.com")
    db.add(user)
    db.commit()
    headers = auth_header(make_token(user.clerk_user_id))
    failed = make_document(db, user, "failed", RAW_INTERNAL, "bad.pdf")
    ready = make_document(db, user, "ready", None, "good.pdf")

    one = client.get(f"/documents/{failed.id}", headers=headers)
    listing = client.get("/documents", headers=headers)

    for response in (one, listing):
        assert response.status_code == 200
        assert "10.0.0.5" not in response.text and "error_message" not in response.text
    assert "temporary problem" in one.json()["failure_reason"]
    by_id = {doc["id"]: doc for doc in listing.json()}
    assert "temporary problem" in by_id[failed.id]["failure_reason"] and by_id[ready.id]["failure_reason"] is None
