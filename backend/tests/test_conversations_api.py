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
from tests.conftest import make_fake_llm
from tests.test_ask_stream import make_streaming_llm, parse_events
from tests.test_retrieve_ask_api import headers_for, use_llm, users  # noqa: F401  (shared fixtures)

QUESTION = "How many vacation days do employees get?"
ANSWER = "Employees get twenty days of paid vacation [1]."


def ask(client, user, **payload):
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
    resp = client.post("/ask/stream", headers=headers_for(users[0]), json={"query": QUESTION})
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

    messages = get_conversation(client, users[0], conversation.id).json()["messages"]
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
    assert get_conversation(client, alice, 99999).status_code == 404
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


def test_new_chat_is_empty_untitled_and_listed(client, users):
    resp = create(client, users[0])
    assert resp.status_code == 201, resp.text
    chat = resp.json()
    assert chat["title"] is None and chat["message_count"] == 0
    assert chat["last_message_at"] == chat["created_at"]

    assert [r["id"] for r in client.get("/conversations", headers=headers_for(users[0])).json()] == [chat["id"]]
    detail = get_conversation(client, users[0], chat["id"]).json()
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


def test_empty_chats_sort_with_chats_that_have_messages(client, users, use_llm):
    use_llm(make_fake_llm(answer=ANSWER))
    alice = users[0]
    older = ask(client, alice)["conversation_id"]
    empty = create(client, alice).json()["id"]
    ids = lambda: [r["id"] for r in client.get("/conversations", headers=headers_for(alice)).json()]

    assert ids() == [empty, older]
    ask(client, alice, conversation_id=older)                       # new activity moves it back to the top
    assert ids() == [older, empty]


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
    assert rename(client, alice, 99999, "x").status_code == 404
    assert client.patch(f"/conversations/{chat['id']}", json={"title": "x"}).status_code == 401
    assert get_conversation(client, alice, chat["id"]).json()["title"] == "alice's chat"


# --- delete ------------------------------------------------------------------------------------------


def test_delete_removes_the_conversation_its_messages_and_citations(client, users, use_llm, db):
    use_llm(make_fake_llm(answer=ANSWER))
    conversation_id = ask(client, users[0])["conversation_id"]
    assert db.query(Message).filter_by(conversation_id=conversation_id).count() == 2

    resp = client.delete(f"/conversations/{conversation_id}", headers=headers_for(users[0]))
    assert resp.status_code == 204 and resp.content == b""

    assert get_conversation(client, users[0], conversation_id).status_code == 404
    assert client.get("/conversations", headers=headers_for(users[0])).json() == []
    db.expire_all()
    assert db.query(Conversation).filter_by(id=conversation_id).count() == 0
    assert db.query(Message).filter_by(conversation_id=conversation_id).count() == 0     # citations went with them


def test_delete_twice_or_unknown_is_404(client, users):
    chat = create(client, users[0]).json()
    assert client.delete(f"/conversations/{chat['id']}", headers=headers_for(users[0])).status_code == 204
    assert client.delete(f"/conversations/{chat['id']}", headers=headers_for(users[0])).status_code == 404
    assert client.delete("/conversations/99999", headers=headers_for(users[0])).status_code == 404


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
    store.add_memory(alice.id, "Works in the Berlin office", conversation_id)

    assert client.delete(f"/conversations/{conversation_id}", headers=headers_for(alice)).status_code == 204

    assert [m.text for m in store.list_memories(alice.id)] == ["Works in the Berlin office"]     # the facts stay
    found = client.post("/retrieve", headers=headers_for(alice), json={"query": QUESTION}).json()["results"]
    assert found                                                                                  # documents still searchable
