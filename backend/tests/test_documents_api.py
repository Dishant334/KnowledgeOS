"""
Documents API on the REAL app (app.main) — INTEGRATION: real Postgres, real
auth dependency with a mocked-Clerk JWT (local RSA key, fake JWKS). Celery
dispatch is patched (no broker/worker here).
"""

from tests.conftest import auth_header, make_token, unique_clerk_id


def test_documents_routes_are_mounted(app):
    paths = app.openapi()["paths"]
    assert "/documents" in paths and "/documents/{document_id}" in paths


def test_authenticated_upload_list_get_delete_on_real_app(client, monkeypatch):
    from app.worker.celery_app import celery_app

    sent = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, args=None, **kw: sent.append((name, args)))
    headers = auth_header(make_token(unique_clerk_id()))

    resp = client.post("/documents", headers=headers,
                       files={"file": ("notes.md", b"# Notes\n\nReal app upload.", "text/markdown")})
    assert resp.status_code == 201, resp.text
    doc = resp.json()
    assert doc["status"] == "pending" and doc["mime_type"] == "text/markdown"
    assert sent == [("ingest_file_task", [doc["id"]])]

    assert [d["id"] for d in client.get("/documents", headers=headers).json()] == [doc["id"]]
    assert client.get(f"/documents/{doc['id']}", headers=headers).status_code == 200
    assert client.delete(f"/documents/{doc['id']}", headers=headers).status_code == 204
    assert client.get(f"/documents/{doc['id']}", headers=headers).status_code == 404


def test_upload_requires_auth_on_real_app(client):
    assert client.post("/documents", files={"file": ("a.md", b"x", "text/markdown")}).status_code == 401
