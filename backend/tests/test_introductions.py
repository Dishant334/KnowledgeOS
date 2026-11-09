"""
Facts a user states about themselves are remembered at once (services/introductions.py + services/ask.py).

Unit tests for the extractor, then the real app over HTTP (test Postgres for the messages and the memory store;
the LLM is fake and must never be called for a pure introduction).
"""

import pytest

from app.db.models import Message
from app.memory import store
from app.services.introductions import GREETING_REPLY, analyze_message, social_reply
from tests.conftest import conversation_pk, make_fake_llm
from tests.test_retrieve_ask_api import chat, headers_for, use_llm, users  # noqa: F401  (shared fixtures)


# --- the extractor -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("message, expected", [
    ("myself dishant kumar", ["Name: Dishant Kumar"]),
    ("my name is Dishant", ["Name: Dishant"]),
    ("hi, I'm Dishant", ["Name: Dishant"]),
    ("Hello! I am dishant", ["Name: Dishant"]),
    ("call me DK", ["Name: DK"]),
    ("my name is McKenzie", ["Name: McKenzie"]),
    ("I am a student", ["Role: student"]),
    ("I work as an engineer", ["Role: engineer"]),
    ("I work at Infosys", ["Works at: Infosys"]),
    ("I work in the Berlin office", ["Works in: the Berlin office"]),
    ("I prefer short answers", ["Prefers: short answers"]),
    ("I'm Dishant and I work at Infosys", ["Name: Dishant", "Works at: Infosys"]),
])
def test_self_facts_are_recognised(message, expected):
    analysis = analyze_message(message)
    assert [f.text for f in analysis.facts] == expected
    assert analysis.only_social is True


@pytest.mark.parametrize("message", [
    "I'm fine", "I am not sure", "I am looking for the policy", "this is great", "it's me", "this is me",
    "I am a bit confused", "im from delhi", "I'm new here", "what is this about", "I am Dishant Kumar Sharma Jr",
    "how many vacation days do I get?", "I'm sorry",
])
def test_look_alikes_are_not_facts(message):
    analysis = analyze_message(message)
    assert analysis.facts == [] and analysis.only_social is False


def test_an_introduction_with_a_question_is_not_only_an_introduction():
    analysis = analyze_message("I'm Dishant, how many vacation days do I get?")
    assert [f.text for f in analysis.facts] == ["Name: Dishant"] and analysis.only_social is False


def test_the_reply_greets_by_name_even_when_memory_is_full():
    analysis = analyze_message("myself dishant kumar")
    assert social_reply(analysis, analysis.facts, False, False).startswith("Hello Dishant Kumar! Nice to meet you. I'll remember your name.")
    full = social_reply(analysis, [], True, False)
    assert full.startswith("Hello Dishant Kumar!") and "memory is full" in full


# --- whole social messages -------------------------------------------------------------------------------------


@pytest.mark.parametrize("message, social", [
    ("hi", ["greeting"]),
    ("hello there", ["greeting"]),
    ("hey how r u", ["greeting", "how_are_you"]),
    ("how are you?", ["how_are_you"]),
    ("what is your name", ["ask_name"]),
    ("who are you?", ["ask_name"]),
    ("good morning! what can you do?", ["greeting", "capabilities"]),
    ("thanks", ["thanks"]),
    ("hello nice to meet you", ["greeting", "nice_to_meet"]),
    ("bye", ["bye"]),
])
def test_social_messages_are_recognised(message, social):
    analysis = analyze_message(message)
    assert analysis.social == social and analysis.only_social is True and analysis.facts == []


def test_one_reply_covers_every_part_of_a_social_message():
    analysis = analyze_message("hello, how are you? my name is Dishant, what's your name?")
    assert [f.text for f in analysis.facts] == ["Name: Dishant"] and analysis.only_social is True
    reply = social_reply(analysis, analysis.facts, False, has_documents=True)
    assert reply.startswith("Hello Dishant!")
    assert "I'm doing well" in reply and "I'm KnowledgeOS" in reply and "I'll remember your name" in reply
    assert reply.endswith("What would you like to know about your documents?")


def test_a_bare_greeting_without_documents_is_the_standard_welcome():
    assert social_reply(analyze_message("hi"), [], False, has_documents=False) == GREETING_REPLY


@pytest.mark.parametrize("message", ["hi, summarise the document", "hello world program in python",
                                     "thanks for the budget numbers, what about Q3?", "what is this about"])
def test_a_real_question_is_never_treated_as_small_talk(message):
    assert analyze_message(message).only_social is False


# --- over HTTP -------------------------------------------------------------------------------------------------


def ask(client, user, text, conversation_id=None):
    body = {"query": text} if conversation_id is None else {"query": text, "conversation_id": conversation_id}
    resp = client.post("/ask", headers=headers_for(user), json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def memories(user):
    return [m.text for m in store.list_memories(user.id)]


def test_an_introduction_in_a_new_chat_is_remembered_and_answered_without_the_llm(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(calls=calls))
    body = ask(client, users[0], "myself dishant kumar")

    assert body["answer"].startswith("Hello Dishant Kumar! Nice to meet you. I'll remember your name.")
    assert body["abstained"] is False and body["citations"] == [] and calls == []
    assert memories(users[0]) == ["Name: Dishant Kumar"]
    [fact] = store.list_memories(users[0].id)
    assert fact.source_conversation_id == conversation_pk(body["conversation_id"])              # "learned in a chat" links to it
    saved = db.query(Message).filter_by(conversation_id=conversation_pk(body["conversation_id"])).order_by(Message.id).all()
    assert [(m.role, m.content) for m in saved] == [("user", "myself dishant kumar"), ("assistant", body["answer"])]


def test_an_introduction_works_in_a_chat_that_has_documents_too(client, users, use_llm):
    calls = []
    use_llm(make_fake_llm(calls=calls))
    body = ask(client, users[0], "I'm Dishant and I work at Infosys", conversation_id=chat(users[0]))
    assert "Dishant" in body["answer"] and "work at Infosys" in body["answer"] and calls == []
    assert sorted(memories(users[0])) == ["Name: Dishant", "Works at: Infosys"]


def test_a_new_name_replaces_the_old_one_and_a_repeat_is_not_stored_twice(client, users, use_llm):
    use_llm(make_fake_llm())
    ask(client, users[0], "my name is Dishant")
    ask(client, users[0], "my name is Dishant")
    assert memories(users[0]) == ["Name: Dishant"]
    ask(client, users[0], "call me DK")
    assert memories(users[0]) == ["Name: DK"]


def test_an_introduction_with_a_question_is_answered_normally_and_still_remembered(client, users, use_llm):
    use_llm(make_fake_llm(answer="Twenty days [1]."))
    body = ask(client, users[0], "I'm Dishant, how many vacation days do employees get?", conversation_id=chat(users[0]))
    assert body["answer"] == "Twenty days [1]." and body["citations"]
    assert memories(users[0]) == ["Name: Dishant"]


def test_a_full_memory_never_breaks_the_reply(client, users, use_llm):
    use_llm(make_fake_llm())
    for i in range(store.MAX_MEMORIES_PER_USER):
        store.add_memory(users[0].id, f"Project note {i}")
    body = ask(client, users[0], "myself dishant kumar")
    assert body["answer"].startswith("Hello Dishant Kumar!") and "memory is full" in body["answer"]
    assert "Name: Dishant Kumar" not in memories(users[0])


def test_a_memory_outage_never_fails_the_request(client, users, use_llm, monkeypatch):
    use_llm(make_fake_llm())

    def down(*_args, **_kwargs):
        raise ConnectionError("memory store down")

    monkeypatch.setattr(store, "list_memories", down)
    body = ask(client, users[0], "myself dishant kumar")
    assert body["answer"].startswith("Hello Dishant Kumar!")


def test_small_talk_in_a_chat_with_documents_never_searches_or_calls_the_llm(client, users, use_llm, monkeypatch):
    import app.services.retrieve as service

    calls = []
    use_llm(make_fake_llm(calls=calls))
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: pytest.fail("no search for small talk"))
    body = ask(client, users[0], "hello, how are you? what's your name?", conversation_id=chat(users[0]))
    assert "I'm doing well" in body["answer"] and "I'm KnowledgeOS" in body["answer"] and calls == []
