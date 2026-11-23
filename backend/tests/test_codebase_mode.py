# CODEBASE-FEATURE (Stage 4): a conversation has a mode ("docs" or "code"), enforced by the SERVER (S12).
#
# API tests use the real app and the real Postgres test DB (Celery dispatch and the LLM are faked).
# Migration tests run against the isolated test DB only.
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.models import Conversation, Document, Message
from app.db.models.conversation_documents import ConversationDocument
from tests.conftest import BACKEND_DIR, conversation_pk, make_fake_llm
from tests.test_retrieve_ask_api import headers_for, use_llm, users  # noqa: F401  (shared fixtures)


@pytest.fixture(autouse=True)
def no_dispatch(monkeypatch):
    """Uploads would hand the file to Celery; here that call does nothing."""
    from app.worker.celery_app import celery_app

    monkeypatch.setattr(celery_app, "send_task", lambda *_, **__: None)


def create_chat(client, user, **body):
    resp = client.post("/conversations", headers=headers_for(user), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def upload(client, user, name, data=b"some bytes", chat=None):
    form = {"conversation_id": str(chat)} if chat is not None else None
    # no content type: the server decides from the extension, like a browser that does not know the type
    return client.post("/documents", headers=headers_for(user), data=form, files={"file": (name, data, "application/octet-stream")})


# --- the mode itself -------------------------------------------------------------------------------------------


def test_a_new_conversation_is_a_docs_conversation_by_default(client, users):
    assert create_chat(client, users[0])["mode"] == "docs"
    assert create_chat(client, users[0], title="named")["mode"] == "docs"


def test_a_conversation_can_be_created_in_code_mode(client, users):
    chat = create_chat(client, users[0], mode="code")
    assert chat["mode"] == "code"
    detail = client.get(f"/conversations/{chat['id']}", headers=headers_for(users[0])).json()
    assert detail["mode"] == "code"


@pytest.mark.parametrize("mode", ["other", "CODE", "", None, 1])
def test_an_unknown_mode_is_rejected(client, users, mode):
    resp = client.post("/conversations", headers=headers_for(users[0]), json={"mode": mode})
    assert resp.status_code == 422


def test_the_conversation_list_shows_the_mode(client, users, db):
    for mode in ("docs", "code"):
        conversation = Conversation(user_id=users[0].id, title=f"{mode} chat", mode=mode)
        db.add(conversation)
        db.flush()
        db.add(Message(conversation_id=conversation.id, role="user", content="q"))
    db.commit()
    rows = client.get("/conversations", headers=headers_for(users[0])).json()
    assert {row["title"]: row["mode"] for row in rows} == {"docs chat": "docs", "code chat": "code"}


def test_the_mode_cannot_be_changed_afterwards(client, users):
    chat = create_chat(client, users[0], mode="code")
    resp = client.patch(f"/conversations/{chat['id']}", headers=headers_for(users[0]), json={"title": "renamed", "mode": "docs"})
    assert resp.status_code == 200 and resp.json()["title"] == "renamed"
    assert resp.json()["mode"] == "code"                 # the extra field is ignored, not applied


# --- S12: the server refuses the wrong kind of file ---------------------------------------------------------------


@pytest.mark.parametrize("name", ["main.py", "App.tsx", "util.cpp", "Main.java", "SRC.PY"])
def test_a_docs_chat_refuses_source_code(client, users, db, name):
    chat = create_chat(client, users[0])["id"]
    resp = upload(client, users[0], name, chat=chat)
    assert resp.status_code == 400
    assert "documents chat" in resp.json()["detail"]
    assert db.query(Document).count() == 0               # nothing was stored


@pytest.mark.parametrize("name", ["report.pdf", "memo.docx", "deck.pptx", "sheet.xlsx", "staff.csv", "page.html", "photo.png"])
def test_a_code_chat_refuses_documents(client, users, db, name):
    chat = create_chat(client, users[0], mode="code")["id"]
    resp = upload(client, users[0], name, chat=chat)
    assert resp.status_code == 400
    assert db.query(Document).count() == 0
    if name != "photo.png":                              # an unsupported type keeps its own, older message
        assert "codebase chat" in resp.json()["detail"]


@pytest.mark.parametrize("name,stored_type", [
    ("main.py", "text/x-code"), ("app.ts", "text/x-code"), ("util.c", "text/x-code"),
    ("README.md", "text/markdown"), ("notes.txt", "text/plain"), ("guide.markdown", "text/markdown"),
])
def test_a_code_chat_accepts_source_code_markdown_and_text(client, users, name, stored_type):
    chat = create_chat(client, users[0], mode="code")["id"]
    resp = upload(client, users[0], name, chat=chat)
    assert resp.status_code == 201, resp.text
    assert resp.json()["mime_type"] == stored_type
    listed = client.get(f"/conversations/{chat}/documents", headers=headers_for(users[0])).json()
    assert [d["filename"] for d in listed] == [name]


@pytest.mark.parametrize("name", ["report.pdf", "memo.docx", "staff.csv", "page.html", "notes.txt", "README.md"])
def test_a_docs_chat_still_accepts_documents(client, users, name):
    chat = create_chat(client, users[0])["id"]
    assert upload(client, users[0], name, chat=chat).status_code == 201


def test_without_a_conversation_both_kinds_are_still_accepted_into_the_library(client, users):
    assert upload(client, users[0], "main.py").status_code == 201
    assert upload(client, users[0], "report.pdf").status_code == 201


def test_someone_elses_chat_is_still_a_404_before_the_mode_is_even_looked_at(client, users):
    alices_code_chat = create_chat(client, users[0], mode="code")["id"]
    assert upload(client, users[1], "report.pdf", chat=alices_code_chat).status_code == 404


def test_the_refusal_attaches_nothing_to_the_chat(client, users, db):
    chat = create_chat(client, users[0], mode="code")["id"]
    upload(client, users[0], "report.pdf", chat=chat)
    assert db.query(ConversationDocument).count() == 0


# the duplicate-bytes path links the user's EXISTING document, which keeps its old name and type: it must be checked too


def test_a_pdf_already_in_the_library_cannot_be_linked_into_a_code_chat_by_renaming_it(client, users):
    library = upload(client, users[0], "report.pdf", b"identical bytes").json()
    assert library["mime_type"] == "application/pdf"
    code_chat = create_chat(client, users[0], mode="code")["id"]

    resp = upload(client, users[0], "innocent.py", b"identical bytes", chat=code_chat)   # same bytes, a code-looking name
    assert resp.status_code == 400 and "codebase chat" in resp.json()["detail"]
    assert client.get(f"/conversations/{code_chat}/documents", headers=headers_for(users[0])).json() == []
    # the library copy is untouched
    assert client.get(f"/documents/{library['id']}", headers=headers_for(users[0])).status_code == 200


def test_a_code_file_already_in_the_library_cannot_be_linked_into_a_docs_chat_by_renaming_it(client, users):
    library = upload(client, users[0], "tool.py", b"identical code bytes").json()
    assert library["mime_type"] == "text/x-code"
    docs_chat = create_chat(client, users[0])["id"]

    resp = upload(client, users[0], "notes.txt", b"identical code bytes", chat=docs_chat)
    assert resp.status_code == 400 and "documents chat" in resp.json()["detail"]
    assert client.get(f"/conversations/{docs_chat}/documents", headers=headers_for(users[0])).json() == []


def test_the_same_kind_of_duplicate_is_still_attached(client, users):
    first = create_chat(client, users[0], mode="code")["id"]
    second = create_chat(client, users[0], mode="code")["id"]
    a = upload(client, users[0], "tool.py", b"shared code", first).json()
    b = upload(client, users[0], "tool.py", b"shared code", second).json()
    assert a["id"] == b["id"]


# --- asking in a code chat that has no files yet --------------------------------------------------------------------


def test_a_code_chat_without_files_asks_for_a_source_file_and_never_calls_the_model(client, users, use_llm):
    calls = []
    use_llm(make_fake_llm(calls=calls))
    chat = create_chat(client, users[0], mode="code")["id"]
    resp = client.post("/ask", headers=headers_for(users[0]), json={"query": "How does login work?", "conversation_id": chat})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["abstained"] is True and body["citations"] == []
    assert "source" in body["answer"].lower() and "document" not in body["answer"].lower()
    assert calls == []


def test_a_docs_chat_without_files_keeps_the_original_reply(client, users, use_llm):
    use_llm(make_fake_llm())
    chat = create_chat(client, users[0])["id"]
    body = client.post("/ask", headers=headers_for(users[0]), json={"query": "What is the leave policy?", "conversation_id": chat}).json()
    assert "add a document" in body["answer"].lower()


def test_the_fixed_reply_is_not_fed_back_to_the_model_as_history(client, users, use_llm):
    from app.services.ask import _without_refused_turns
    from app.services.small_talk import NEED_SOURCE_REPLY

    history = [("user", "How does login work?"), ("assistant", NEED_SOURCE_REPLY)]
    assert _without_refused_turns(history) == []


# --- the column and the migration -----------------------------------------------------------------------------------------


def test_the_database_guarantees_a_valid_mode(db, users):
    plain = Conversation(user_id=users[0].id)
    db.add(plain)
    db.commit()
    db.refresh(plain)
    assert plain.mode == "docs"                            # the default

    db.execute(text("INSERT INTO conversations (user_id, created_at, updated_at) VALUES (:u, now(), now())"), {"u": users[0].id})
    db.commit()
    assert db.execute(text("SELECT mode FROM conversations ORDER BY id DESC LIMIT 1")).scalar() == "docs"   # server default

    db.add(Conversation(user_id=users[0].id, mode="other"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_conversation_that_existed_before_the_migration_becomes_a_docs_conversation(db, users):
    """Downgrade one step, insert a row the old way (no mode column), upgrade: the row reads 'docs'."""
    from alembic import command
    from alembic.config import Config

    from app.db.database import engine

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    user_id = users[0].id
    db.close()
    command.downgrade(cfg, "-1")
    try:
        with engine.begin() as conn:
            columns = {row[0] for row in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'conversations'"))}
            assert "mode" not in columns
            conn.execute(text("INSERT INTO conversations (user_id, title, created_at, updated_at) VALUES (:u, 'old chat', now(), now())"),
                         {"u": user_id})
    finally:
        command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT mode FROM conversations WHERE title = 'old chat'")).scalar() == "docs"
        nullable = conn.execute(text(
            "SELECT is_nullable FROM information_schema.columns WHERE table_name = 'conversations' AND column_name = 'mode'")).scalar()
        assert nullable == "NO"
