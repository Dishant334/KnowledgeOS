"""
Document persistence — INTEGRATION tests against the isolated Postgres test DB
(<dev_db>_test, migrated to head by conftest). No DB mocking; only the
authenticated user is injected via dependency override for HTTP-level tests.
"""

import asyncio
import hashlib
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import Headers, UploadFile

from app.db.models import Document, DocumentBlob, User
from tests.conftest import BACKEND_DIR, unique_clerk_id

PDF = "application/pdf"


def _user(db, email="u@example.com") -> User:
    user = User(clerk_user_id=unique_clerk_id(), email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _document(db, user, data=b"hello", **overrides) -> Document:
    digest = hashlib.sha256(data).hexdigest()
    fields = dict(
        user_id=user.id, filename="a.pdf", mime_type=PDF, file_size=len(data),
        status="pending", document_hash=digest, storage_key=digest,
    )
    fields.update(overrides)
    doc = Document(**fields)
    db.add(doc)
    db.flush()
    db.add(DocumentBlob(document_id=doc.id, data=data))
    db.commit()
    db.refresh(doc)
    return doc


def _alembic_cfg():
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


# --- Schema / migration consistency -----------------------------------------


def test_models_match_migrated_schema():
    """`alembic check` equivalent: raises if models and DB schema differ."""
    from alembic import command

    command.check(_alembic_cfg())


def test_externally_managed_message_store_is_never_dropped():
    """Autogenerate must ignore langchain_postgres' message_store table."""
    from alembic import command
    from app.db.database import engine

    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS message_store (id SERIAL PRIMARY KEY)"))
    try:
        command.check(_alembic_cfg())  # would raise with remove_table('message_store')
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS message_store"))  # test DB only


def test_migration_downgrade_upgrade_roundtrip():
    """Runs only against the isolated test DB (tables are empty between tests)."""
    from alembic import command
    from alembic.script import ScriptDirectory

    cfg = _alembic_cfg()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
    from app.db.database import engine

    with engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == head
    command.check(cfg)


# --- Model-level persistence ---------------------------------------------------


def test_document_and_blob_roundtrip(db):
    user = _user(db)
    doc = _document(db, user, data=b"%PDF-1.4 bytes")
    db.expire_all()
    loaded = db.get(Document, doc.id)
    assert loaded.blob.data == b"%PDF-1.4 bytes"
    assert loaded.user.id == user.id
    assert loaded.error_message is None
    assert loaded.status == "pending"


@pytest.mark.parametrize("missing", ["document_hash", "storage_key"])
def test_required_columns_not_null(db, missing):
    user = _user(db)
    with pytest.raises(IntegrityError):
        _document(db, user, **{missing: None})
    db.rollback()


def test_same_hash_rejected_for_same_user(db):
    user = _user(db)
    _document(db, user, data=b"dup")
    with pytest.raises(IntegrityError):
        _document(db, user, data=b"dup")
    db.rollback()


def test_same_hash_allowed_for_different_users(db):
    a, b = _user(db, "a@example.com"), _user(db, "b@example.com")
    da = _document(db, a, data=b"shared")
    dbb = _document(db, b, data=b"shared")
    assert da.id != dbb.id and da.document_hash == dbb.document_hash


def test_blob_requires_existing_document(db):
    db.add(DocumentBlob(document_id=999_999, data=b"x"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_deleting_document_cascades_blob(db):
    doc = _document(db, _user(db))
    doc_id = doc.id
    db.delete(doc)
    db.commit()
    assert db.get(DocumentBlob, doc_id) is None


def test_deleting_user_cascades_documents_and_blobs(db):
    user = _user(db)
    doc_ids = [_document(db, user, data=f"f{i}".encode()).id for i in range(3)]
    db.delete(user)
    db.commit()
    assert db.query(Document).filter(Document.id.in_(doc_ids)).count() == 0
    assert db.query(DocumentBlob).filter(DocumentBlob.document_id.in_(doc_ids)).count() == 0


def test_raw_sql_user_delete_cascades_too(db):
    """DB-level ON DELETE CASCADE works even without the ORM."""
    user = _user(db)
    doc_id = _document(db, user).id
    db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    db.commit()
    assert db.execute(text("SELECT count(*) FROM document_blobs WHERE document_id = :d"), {"d": doc_id}).scalar() == 0


# --- Service-level (create_document) ------------------------------------------


def _upload(data: bytes, filename="report.pdf", content_type=PDF) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename, headers=Headers({"content-type": content_type}))


def _create(db, user, data, **kw):
    from app.services.document import create_document

    return asyncio.run(create_document(db=db, user=user, file=_upload(data, **kw)))


def test_service_persists_document_and_blob(db):
    user = _user(db)
    doc = _create(db, user, b"%PDF service")
    assert doc.document_hash == hashlib.sha256(b"%PDF service").hexdigest()
    assert doc.storage_key == doc.document_hash
    assert doc.file_size == len(b"%PDF service")
    assert db.get(DocumentBlob, doc.id).data == b"%PDF service"


def test_service_reupload_same_user_returns_existing(db):
    user = _user(db)
    first = _create(db, user, b"same")
    second = _create(db, user, b"same", filename="renamed.pdf")
    assert first.id == second.id
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_service_dedup_never_crosses_users(db):
    """Previously returned user A's document to user B."""
    a, b = _user(db, "a@example.com"), _user(db, "b@example.com")
    doc_a = _create(db, a, b"same content")
    doc_b = _create(db, b, b"same content")
    assert doc_b.id != doc_a.id
    assert doc_b.user_id == b.id
    assert db.get(DocumentBlob, doc_b.id).data == b"same content"


def test_service_concurrent_duplicate_upload_returns_existing(db, monkeypatch):
    """Simulate losing the race: the pre-check misses, the unique constraint fires."""
    import app.services.document as svc

    user = _user(db)
    winner = _create(db, user, b"race")
    real = svc._find_user_document_by_hash
    calls = {"n": 0}

    def miss_first(*args):
        calls["n"] += 1
        return None if calls["n"] == 1 else real(*args)

    monkeypatch.setattr(svc, "_find_user_document_by_hash", miss_first)
    loser = _create(db, user, b"race")
    assert loser.id == winner.id
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


# --- HTTP level (documents router on a test app; auth overridden) -------------


@pytest.fixture
def documents_client(db):
    from app.dependencies.auth import get_current_user
    from app.db.database import get_db
    from app.routers.document import router

    state = {"user": None}
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_current_user] = lambda: state["user"]
    test_app.dependency_overrides[get_db] = lambda: db
    return TestClient(test_app), state


def test_http_upload_list_get_delete(db, documents_client):
    client, state = documents_client
    state["user"] = _user(db)

    resp = client.post("/documents", files={"file": ("a.pdf", b"%PDF http", PDF)})
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]
    assert resp.json()["status"] == "pending"

    assert [d["id"] for d in client.get("/documents").json()] == [doc_id]
    assert client.get(f"/documents/{doc_id}").status_code == 200

    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get(f"/documents/{doc_id}").status_code == 404
    assert db.get(DocumentBlob, doc_id) is None


def test_http_users_cannot_see_each_others_documents(db, documents_client):
    client, state = documents_client
    state["user"] = _user(db, "a@example.com")
    doc_id = client.post("/documents", files={"file": ("a.pdf", b"%PDF secret", PDF)}).json()["id"]

    state["user"] = _user(db, "b@example.com")
    assert client.get(f"/documents/{doc_id}").status_code == 404
    assert client.delete(f"/documents/{doc_id}").status_code == 404
    assert client.get("/documents").json() == []
    # B uploading identical bytes gets B's own document, not A's.
    resp = client.post("/documents", files={"file": ("b.pdf", b"%PDF secret", PDF)})
    assert resp.status_code == 201 and resp.json()["id"] != doc_id
