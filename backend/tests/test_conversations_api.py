"""
Persisted citations and the conversation endpoints:

    GET /conversations          the sidebar list
    GET /conversations/{id}     the whole chat, citations included, in ONE request

Same real app, Postgres test DB, Qdrant test collection and models as test_retrieve_ask_api.py;
only the LLM is fake.
"""

import pytest

from app.augmentation.citation_mapper import SNIPPET_CHARS, make_snippet
from app.db.models import Conversation, Message
from app.memory import store
from tests.conftest import CORPUS_DOCUMENTS, attach_documents, chat_with_documents, conversation_pk, conversation_public_id, make_fake_llm
from tests.test_ask_stream import make_streaming_llm, parse_events
from tests.test_retrieve_ask_api import headers_for, use_llm, users  # noqa: F401  (shared fixtures)

QUESTION = "How many vacation days do employees get?"
ANSWER = "Employees get twenty days of paid vacation [1]."


def ask(client, user, **payload):
    """Asks QUESTION into the given conversation (its documents attached) or into a new chat with the user's documents."""
    if "conversation_id" in payload:
        payload["conversation_id"] = conversation_public_id(payload["conversation_id"])
        attach_documents(payload["conversation_id"], user.id, CORPUS_DOCUMENTS[user.id])
    else:
        payload["conversation_id"] = chat_with_documents(user.id, CORPUS_DOCUMENTS[user.id])
    resp = client.post("/ask", headers=headers_for(user), json={"query": QUESTION, **payload})
    assert resp.status_code == 200, resp.text
    return resp.json()


def get_conversation(client, user, conversation_id):
    return client.get(f"/conversations/{conversation_id}", headers=headers_for(user))


# --- a conversation comes back whole, with the citations it was answered with -----------------------


def test_get_conversation_returns_messages_with_their_citations(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    answer = ask(client, users[0])

    resp = get_conversation(client, users[0], answer["conversation_id"])
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["id"] == answer["conversation_id"] and body["title"] == QUESTION
    assert {"created_at", "last_message_at"} <= set(body)

    user_message, assistant_message = body["messages"]
    assert (user_message["role"], user_message["content"], user_message["citations"]) == ("user", QUESTION, [])
    assert assistant_message["role"] == "assistant" and assistant_message["content"] == ANSWER
    assert assistant_message["id"] == answer["message_id"]
    # exactly what /ask returned at the time, so a reloaded chat shows the same source cards
    assert assistant_message["citations"] == answer["citations"]
    first = assistant_message["citations"][0]
    assert first["marker"] == "[1]" and first["document_id"] == 10 and first["source_name"] == "handbook.pdf"


def test_citations_carry_a_snippet_of_the_cited_passage(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    answer = ask(client, users[0])

    snippet = get_conversation(client, users[0], answer["conversation_id"]).json()["messages"][1]["citations"][0]["snippet"]
    assert "twenty days of paid vacation" in snippet
    assert len(snippet) <= SNIPPET_CHARS + 3          # the cap plus the "..." marker


def test_messages_come_back_oldest_first_across_turns(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    first = ask(client, users[0])
    ask(client, users[0], conversation_id=first["conversation_id"])

    messages = get_conversation(client, users[0], first["conversation_id"]).json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert [m["id"] for m in messages] == sorted(m["id"] for m in messages)
    assert messages[1]["citations"] and messages[3]["citations"]


def test_streamed_answers_store_their_citations_too(client, users, use_llm):
    use_llm(make_streaming_llm())
    chat = chat_with_documents(users[0].id, CORPUS_DOCUMENTS[1])
    resp = client.post("/ask/stream", headers=headers_for(users[0]), json={"query": QUESTION, "conversation_id": chat})
    done = parse_events(resp.text)[-1][1]

    stored = get_conversation(client, users[0], done["conversation_id"]).json()["messages"][1]
    assert stored["content"] == done["answer"] and stored["citations"] == done["citations"] != []


def test_a_refusal_has_no_citations(client, users, use_llm):
    use_llm(make_fake_llm(answer="I don't have enough information to answer that."))
    answer = ask(client, users[0])

    messages = get_conversation(client, users[0], answer["conversation_id"]).json()["messages"]
    assert messages[1]["citations"] == []


def test_answers_saved_before_citations_were_stored_come_back_with_an_empty_list(client, users, db):
    conversation = Conversation(user_id=users[0].id, title="old chat")
    db.add(conversation)
    db.flush()
    db.add(Message(conversation_id=conversation.id, role="user", content="q"))
    db.add(Message(conversation_id=conversation.id, role="assistant", content="old answer [1]"))   # citations NULL
    db.commit()

    messages = get_conversation(client, users[0], conversation.public_id).json()["messages"]
    assert [m["citations"] for m in messages] == [[], []]


# --- who may see what ------------------------------------------------------------------------------


def test_endpoints_require_auth(client):
    assert client.get("/conversations").status_code == 401
    assert client.get("/conversations/1").status_code == 401


def test_another_users_or_unknown_conversation_is_404(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice, bob = users
    conversation_id = ask(client, alice)["conversation_id"]

    assert get_conversation(client, bob, conversation_id).status_code == 404
    assert get_conversation(client, alice, "00000000-0000-4000-8000-000000000000").status_code == 404
    assert get_conversation(client, alice, conversation_id).status_code == 200


# --- the sidebar list --------------------------------------------------------------------------------


def test_list_has_only_my_conversations_with_counts(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice, bob = users
    mine = ask(client, alice)["conversation_id"]
    ask(client, alice, conversation_id=mine)
    ask(client, bob)

    rows = client.get("/conversations", headers=headers_for(alice)).json()
    assert [(r["id"], r["message_count"], r["title"]) for r in rows] == [(mine, 4, QUESTION)]
    assert {"created_at", "last_message_at"} <= set(rows[0])

    assert len(client.get("/conversations", headers=headers_for(bob)).json()) == 1


def test_list_is_ordered_by_the_newest_message(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice = users[0]
    first = ask(client, alice)["conversation_id"]
    second = ask(client, alice)["conversation_id"]
    assert [r["id"] for r in client.get("/conversations", headers=headers_for(alice)).json()] == [second, first]

    ask(client, alice, conversation_id=first)               # the older chat becomes the most recent one
    assert [r["id"] for r in client.get("/conversations", headers=headers_for(alice)).json()] == [first, second]


def test_list_pagination(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice = users[0]
    ids = [ask(client, alice)["conversation_id"] for _ in range(3)]
    newest_first = list(reversed(ids))

    page = lambda **q: [r["id"] for r in client.get("/conversations", headers=headers_for(alice), params=q).json()]
    assert page(limit=2) == newest_first[:2]
    assert page(limit=2, offset=2) == newest_first[2:]
    assert page(offset=3) == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_validates_paging(client, users, params):
    assert client.get("/conversations", headers=headers_for(users[0]), params=params).status_code == 422


def test_list_is_empty_for_a_new_user(client, users):
    assert client.get("/conversations", headers=headers_for(users[0])).json() == []


# --- snippets (no database needed) ---------------------------------------------------------------------


def test_make_snippet_tidies_whitespace_and_marks_cuts():
    assert make_snippet("short   text\n\nhere") == "short text here"
    long = make_snippet("word " * 500)
    assert long.endswith("...") and len(long) <= SNIPPET_CHARS + 3
    assert make_snippet("x" * SNIPPET_CHARS) == "x" * SNIPPET_CHARS          # exactly at the cap: not cut


# --- new chat -----------------------------------------------------------------------------------------


def create(client, user, **body):
    return client.post("/conversations", headers=headers_for(user), json=body or None)


def test_new_chat_is_empty_untitled_and_not_listed_until_it_has_a_message(client, users):
    resp = create(client, users[0])
    assert resp.status_code == 201, resp.text
    chat = resp.json()
    assert chat["title"] is None and chat["message_count"] == 0
    assert chat["last_message_at"] == chat["created_at"]

    assert client.get("/conversations", headers=headers_for(users[0])).json() == []      # empty chats are not listed
    detail = get_conversation(client, users[0], chat["id"]).json()                        # but it can be opened
    assert detail["messages"] == [] and detail["title"] is None


def test_new_chat_can_be_created_with_a_title(client, users):
    chat = create(client, users[0], title="  Vacation planning  ").json()
    assert chat["title"] == "Vacation planning"                          # trimmed


@pytest.mark.parametrize("title", ["", "   ", "x" * 256])
def test_new_chat_rejects_a_blank_or_too_long_title(client, users, title):
    assert create(client, users[0], title=title).status_code == 422


def test_new_chat_requires_auth(client):
    assert client.post("/conversations").status_code == 401


def test_the_first_question_names_an_untitled_chat_and_stores_citations(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    chat = create(client, users[0]).json()

    answer = ask(client, users[0], conversation_id=chat["id"])
    assert answer["conversation_id"] == chat["id"]

    detail = get_conversation(client, users[0], chat["id"]).json()
    assert detail["title"] == QUESTION
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["citations"] == answer["citations"] != []

    ask(client, users[0], query="A different second question?", conversation_id=chat["id"])
    assert get_conversation(client, users[0], chat["id"]).json()["title"] == QUESTION      # named once


def test_streaming_into_a_new_chat_names_it_too(client, users, use_llm):
    use_llm(make_streaming_llm())
    chat = create(client, users[0]).json()
    attach_documents(chat["id"], users[0].id, CORPUS_DOCUMENTS[1])
    resp = client.post("/ask/stream", headers=headers_for(users[0]), json={"query": QUESTION, "conversation_id": chat["id"]})
    assert parse_events(resp.text)[-1][0] == "done"
    assert get_conversation(client, users[0], chat["id"]).json()["title"] == QUESTION


def test_a_title_given_or_set_by_renaming_is_never_replaced_by_a_question(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    titled = create(client, users[0], title="My own title").json()
    ask(client, users[0], conversation_id=titled["id"])
    assert get_conversation(client, users[0], titled["id"]).json()["title"] == "My own title"

    untitled = create(client, users[0]).json()
    client.patch(f"/conversations/{untitled['id']}", headers=headers_for(users[0]), json={"title": "Renamed first"})
    ask(client, users[0], conversation_id=untitled["id"])
    assert get_conversation(client, users[0], untitled["id"]).json()["title"] == "Renamed first"


def test_an_empty_chat_appears_in_the_list_once_it_gets_its_first_message(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice = users[0]
    older = ask(client, alice)["conversation_id"]
    empty = create(client, alice).json()["id"]
    ids = lambda: [r["id"] for r in client.get("/conversations", headers=headers_for(alice)).json()]

    assert ids() == [older]                                          # the empty chat is not listed
    ask(client, alice, conversation_id=empty)
    assert ids() == [empty, older]                                   # its first question puts it on top


# --- rename ------------------------------------------------------------------------------------------


def rename(client, user, conversation_id, title):
    return client.patch(f"/conversations/{conversation_id}", headers=headers_for(user), json={"title": title})


def test_rename_changes_the_title_everywhere(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    conversation_id = ask(client, users[0])["conversation_id"]

    resp = rename(client, users[0], conversation_id, "  Vacation days  ")
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Vacation days" and resp.json()["message_count"] == 2

    assert get_conversation(client, users[0], conversation_id).json()["title"] == "Vacation days"
    assert client.get("/conversations", headers=headers_for(users[0])).json()[0]["title"] == "Vacation days"


@pytest.mark.parametrize("body", [{"title": ""}, {"title": "   "}, {"title": "x" * 256}, {}])
def test_rename_validates_the_title(client, users, body):
    chat = create(client, users[0]).json()
    resp = client.patch(f"/conversations/{chat['id']}", headers=headers_for(users[0]), json=body)
    assert resp.status_code == 422


def test_rename_is_limited_to_the_owner(client, users):
    alice, bob = users
    chat = create(client, alice, title="alice's chat").json()

    assert rename(client, bob, chat["id"], "hacked").status_code == 404
    assert rename(client, alice, "00000000-0000-4000-8000-000000000000", "x").status_code == 404
    assert client.patch(f"/conversations/{chat['id']}", json={"title": "x"}).status_code == 401
    assert get_conversation(client, alice, chat["id"]).json()["title"] == "alice's chat"


# --- delete ------------------------------------------------------------------------------------------


def test_delete_removes_the_conversation_its_messages_and_citations(client, users, use_llm, db):
    use_llm(make_fake_llm(answer=ANSWER))
    conversation_id = ask(client, users[0])["conversation_id"]
    assert db.query(Message).filter_by(conversation_id=conversation_pk(conversation_id)).count() == 2

    resp = client.delete(f"/conversations/{conversation_id}", headers=headers_for(users[0]))
    assert resp.status_code == 204 and resp.content == b""

    assert get_conversation(client, users[0], conversation_id).status_code == 404
    assert client.get("/conversations", headers=headers_for(users[0])).json() == []
    db.expire_all()
    assert db.query(Conversation).filter_by(public_id=conversation_id).count() == 0
    assert db.query(Message).filter_by(conversation_id=conversation_pk(conversation_id)).count() == 0     # citations went with them


def test_delete_twice_or_unknown_is_404(client, users):
    chat = create(client, users[0]).json()
    assert client.delete(f"/conversations/{chat['id']}", headers=headers_for(users[0])).status_code == 204
    assert client.delete(f"/conversations/{chat['id']}", headers=headers_for(users[0])).status_code == 404
    assert client.delete(f"/conversations/{"00000000-0000-4000-8000-000000000000"}", headers=headers_for(users[0])).status_code == 404


def test_delete_is_limited_to_the_owner(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice, bob = users
    conversation_id = ask(client, alice)["conversation_id"]

    assert client.delete(f"/conversations/{conversation_id}", headers=headers_for(bob)).status_code == 404
    assert client.delete(f"/conversations/{conversation_id}").status_code == 401
    assert len(get_conversation(client, alice, conversation_id).json()["messages"]) == 2     # untouched


def test_delete_only_removes_that_conversation(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice = users[0]
    keep, drop = ask(client, alice)["conversation_id"], ask(client, alice)["conversation_id"]

    client.delete(f"/conversations/{drop}", headers=headers_for(alice))
    assert [r["id"] for r in client.get("/conversations", headers=headers_for(alice)).json()] == [keep]
    assert len(get_conversation(client, alice, keep).json()["messages"]) == 2


def test_delete_keeps_documents_and_long_term_memory(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice = users[0]
    conversation_id = ask(client, alice)["conversation_id"]
    store.add_memory(alice.id, "Works in the Berlin office", conversation_pk(conversation_id))

    assert client.delete(f"/conversations/{conversation_id}", headers=headers_for(alice)).status_code == 204

    assert [m.text for m in store.list_memories(alice.id)] == ["Works in the Berlin office"]     # the facts stay
    found = client.post("/retrieve", headers=headers_for(alice), json={"query": QUESTION}).json()["results"]
    assert found                                                                                  # documents still searchable


# --- documents attached to a conversation, and abandoned empty chats ------------------------------------------


@pytest.fixture
def no_dispatch(monkeypatch):
    """Uploads would hand the file to Celery; here that call does nothing."""
    from app.worker.celery_app import celery_app

    monkeypatch.setattr(celery_app, "send_task", lambda *_, **__: None)


@pytest.fixture
def no_vectors(monkeypatch):
    """Deleting a document also deletes its Qdrant points; record the calls instead."""
    import app.services.document as documents

    deleted = []
    monkeypatch.setattr(documents, "delete_document_points", deleted.append)
    return deleted


def upload(client, user, name, data, conversation_id=None):
    form = {"conversation_id": str(conversation_id)} if conversation_id is not None else None
    return client.post("/documents", headers=headers_for(user), data=form, files={"file": (name, data, "text/plain")})


@pytest.mark.usefixtures("no_dispatch")
def test_an_upload_with_a_conversation_id_is_attached_to_that_chat(client, users):
    chat = create(client, users[0]).json()["id"]
    doc = upload(client, users[0], "notes.txt", b"office opens at eight", chat).json()

    listed = client.get(f"/conversations/{chat}/documents", headers=headers_for(users[0]))
    assert listed.status_code == 200 and [d["id"] for d in listed.json()] == [doc["id"]]
    assert listed.json()[0]["filename"] == "notes.txt"


@pytest.mark.usefixtures("no_dispatch")
def test_the_same_file_in_a_second_chat_attaches_the_existing_document(client, users, db):
    from app.db.models import ConversationDocument

    first, second = create(client, users[0]).json()["id"], create(client, users[0]).json()["id"]
    a = upload(client, users[0], "notes.txt", b"same bytes", first).json()
    b = upload(client, users[0], "notes.txt", b"same bytes", second).json()

    assert a["id"] == b["id"]                                         # one document, two chats
    links = {(link.conversation_id, link.uploaded_here) for link in db.query(ConversationDocument).all()}
    assert links == {(conversation_pk(first), True), (conversation_pk(second), False)}                  # only the first chat created it


@pytest.mark.usefixtures("no_dispatch")
def test_uploading_into_someone_elses_chat_is_404_and_saves_nothing(client, users, db):
    from app.db.models import Document

    alices_chat = create(client, users[0]).json()["id"]
    assert upload(client, users[1], "x.txt", b"bob", alices_chat).status_code == 404
    assert upload(client, users[0], "x.txt", b"alice", "00000000-0000-4000-8000-000000000000").status_code == 404
    assert db.query(Document).count() == 0
    assert client.get(f"/conversations/{alices_chat}/documents", headers=headers_for(users[1])).status_code == 404


@pytest.mark.usefixtures("no_dispatch")
def test_an_upload_without_a_conversation_id_is_attached_to_nothing(client, users, db):
    from app.db.models import ConversationDocument

    assert upload(client, users[0], "x.txt", b"library only").status_code == 201
    assert db.query(ConversationDocument).count() == 0


@pytest.mark.usefixtures("no_dispatch")
def test_deleting_a_document_removes_it_from_its_chats(client, users, db, no_vectors):
    from app.db.models import ConversationDocument

    chat = create(client, users[0]).json()["id"]
    doc = upload(client, users[0], "x.txt", b"bytes", chat).json()
    assert client.delete(f"/documents/{doc['id']}", headers=headers_for(users[0])).status_code == 204
    assert db.query(ConversationDocument).count() == 0
    assert client.get(f"/conversations/{chat}/documents", headers=headers_for(users[0])).json() == []


@pytest.mark.usefixtures("no_dispatch")
def test_deleting_a_chat_keeps_its_documents(client, users, db, use_llm):
    from app.db.models import ConversationDocument, Document

    use_llm(make_fake_llm(answer=ANSWER))
    chat = create(client, users[0]).json()["id"]
    upload(client, users[0], "x.txt", b"bytes", chat)
    ask(client, users[0], conversation_id=chat)
    assert client.delete(f"/conversations/{chat}", headers=headers_for(users[0])).status_code == 204
    assert db.query(Document).count() == 3                          # x.txt + the two corpus rows the helper added
    assert db.query(ConversationDocument).count() == 0


@pytest.mark.usefixtures("no_dispatch")
def test_discarding_an_empty_chat_deletes_it_with_the_files_uploaded_only_into_it(client, users, db, no_vectors):
    from app.db.models import Conversation, Document

    used = create(client, users[0]).json()["id"]
    shared = upload(client, users[0], "shared.txt", b"in two chats", used).json()
    library = upload(client, users[0], "library.txt", b"uploaded before, no chat").json()

    empty = create(client, users[0]).json()["id"]
    own = upload(client, users[0], "own.txt", b"only here", empty).json()
    upload(client, users[0], "shared.txt", b"in two chats", empty)          # attaches the existing one
    upload(client, users[0], "library.txt", b"uploaded before, no chat", empty)

    assert client.post(f"/conversations/{empty}/discard", headers=headers_for(users[0])).status_code == 204

    assert db.get(Conversation, conversation_pk(empty)) is None
    remaining = {d.id for d in db.query(Document).all()}
    assert own["id"] not in remaining                                         # created in that chat: gone
    assert {shared["id"], library["id"]} <= remaining                         # used elsewhere / already in library: kept
    assert no_vectors == [own["id"]]                                          # its search vectors were deleted too


def test_a_chat_with_messages_can_never_be_discarded(client, users, use_llm, db):
    use_llm(make_fake_llm(answer=ANSWER))
    chat = ask(client, users[0])["conversation_id"]
    resp = client.post(f"/conversations/{chat}/discard", headers=headers_for(users[0]))
    assert resp.status_code == 409
    assert get_conversation(client, users[0], chat).status_code == 200
    assert client.post(f"/conversations/{chat}/discard", headers=headers_for(users[1])).status_code == 404


@pytest.mark.usefixtures("no_dispatch")
def test_old_empty_chats_are_swept_away_with_their_own_files(client, users, db, no_vectors, use_llm):
    from datetime import datetime, timedelta

    from app.db.models import Conversation, Document
    from app.services.conversations import ABANDONED_AFTER

    use_llm(make_fake_llm(answer=ANSWER))
    stale = create(client, users[0]).json()["id"]
    fresh = create(client, users[0]).json()["id"]
    used = ask(client, users[0])["conversation_id"]
    stale_doc = upload(client, users[0], "stale.txt", b"left behind", stale).json()
    db.query(Conversation).filter_by(public_id=stale).update({"created_at": datetime.utcnow() - ABANDONED_AFTER - timedelta(minutes=1)})
    db.commit()

    listed = client.get("/conversations", headers=headers_for(users[0])).json()       # the list request sweeps

    assert [c["id"] for c in listed] == [used]
    db.expire_all()
    assert db.get(Conversation, conversation_pk(stale)) is None and db.get(Document, stale_doc["id"]) is None
    assert db.get(Conversation, conversation_pk(fresh)) is not None                                     # recent empty chat: kept for now


# --- public conversation ids -------------------------------------------------------------------------------------


def test_conversation_ids_are_random_uuids_and_integer_ids_are_refused(client, users, use_llm):
    import uuid

    use_llm(make_fake_llm(answer=ANSWER))
    first = ask(client, users[0])["conversation_id"]
    second = ask(client, users[0])["conversation_id"]

    for public in (first, second):
        assert uuid.UUID(public).version == 4                                   # random, not 1, 2, 3...
    listed = [c["id"] for c in client.get("/conversations", headers=headers_for(users[0])).json()]
    assert set(listed) == {first, second}

    internal = conversation_pk(first)                                           # the database's own number
    assert get_conversation(client, users[0], internal).status_code == 422      # is never accepted by the API
    assert client.post("/ask", headers=headers_for(users[0]), json={"query": QUESTION, "conversation_id": internal}).status_code == 422
    assert get_conversation(client, users[0], first).status_code == 200
