"""
Long-term memory learned once per conversation (services/conversation_memory.py, POST /conversations/{id}/remember,
and the every-6-answers safety net inside /ask). Real app, test Postgres (messages + memory store), fake LLM.
"""

import pytest

from app.db.models import Conversation
from app.memory import store
from app.services.conversation_memory import REMEMBER_EVERY_ANSWERS
from tests.conftest import conversation_pk, make_fake_llm
from tests.test_retrieve_ask_api import chat, headers_for, use_llm, users  # noqa: F401  (shared fixtures)

MEMORY_MARKER = "You maintain the long-term memory"


def ask(client, user, text, conversation_id):
    resp = client.post("/ask", headers=headers_for(user), json={"query": text, "conversation_id": conversation_id})
    assert resp.status_code == 200, resp.text
    return resp.json()


def remember(client, user, conversation_id):
    return client.post(f"/conversations/{conversation_id}/remember", headers=headers_for(user))


def memory_calls(calls):
    return [c for c in calls if MEMORY_MARKER in c]


def test_leaving_a_chat_learns_its_facts_into_the_one_memory(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(calls=calls, memories_json='["Works on the leave policy rollout"]'))
    conversation_id = chat(users[0])
    ask(client, users[0], "I am rolling out the new leave policy. How many vacation days do employees get?", conversation_id)
    assert memory_calls(calls) == []                                  # not after a single answer

    resp = remember(client, users[0], conversation_id)

    assert resp.status_code == 202 and resp.json() == {"queued": True}
    assert [m.text for m in store.list_memories(users[0].id)] == ["Works on the leave policy rollout"]
    [prompt] = memory_calls(calls)
    assert "rolling out the new leave policy" in prompt                # the conversation's messages were given to it
    db.expire_all()
    assert db.get(Conversation, conversation_pk(conversation_id)).remembered_until_message_id is not None


def test_the_same_messages_never_cost_a_second_call(client, users, use_llm):
    calls = []
    use_llm(make_fake_llm(calls=calls, memories_json='["Prefers short answers"]'))
    conversation_id = chat(users[0])
    ask(client, users[0], "How many vacation days do employees get?", conversation_id)
    remember(client, users[0], conversation_id)
    assert len(memory_calls(calls)) == 1

    assert remember(client, users[0], conversation_id).json() == {"queued": False}
    assert len(memory_calls(calls)) == 1                              # nothing new: no LLM call

    ask(client, users[0], "And can unused days be carried over?", conversation_id)
    remember(client, users[0], conversation_id)
    assert len(memory_calls(calls)) == 2                              # new messages: one more


def test_a_chat_of_only_small_talk_makes_no_llm_call(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(calls=calls))
    conversation_id = chat(users[0])
    ask(client, users[0], "hi", conversation_id)
    ask(client, users[0], "how are you?", conversation_id)

    remember(client, users[0], conversation_id)

    assert calls == []
    db.expire_all()
    assert db.get(Conversation, conversation_pk(conversation_id)).remembered_until_message_id is not None   # and not looked at again


def test_long_chats_are_remembered_every_few_answers_without_leaving(client, users, use_llm):
    calls = []
    use_llm(make_fake_llm(calls=calls, memories_json='["Studies network security"]'))
    conversation_id = chat(users[0])
    for i in range(REMEMBER_EVERY_ANSWERS - 1):
        ask(client, users[0], f"Question number {i} about vacation days?", conversation_id)
    assert memory_calls(calls) == []

    ask(client, users[0], "One more question about vacation days?", conversation_id)

    assert len(memory_calls(calls)) == 1
    assert [m.text for m in store.list_memories(users[0].id)] == ["Studies network security"]


def test_a_failed_memory_step_changes_nothing_and_is_retried(client, users, use_llm, db):
    use_llm(make_fake_llm(memories_json="this is not a JSON list"))
    store.add_memory(users[0].id, "Works in the Berlin office")
    conversation_id = chat(users[0])
    ask(client, users[0], "How many vacation days do employees get?", conversation_id)

    assert remember(client, users[0], conversation_id).status_code == 202

    assert [m.text for m in store.list_memories(users[0].id)] == ["Works in the Berlin office"]
    db.expire_all()
    assert db.get(Conversation, conversation_pk(conversation_id)).remembered_until_message_id is None        # tried again next time


def test_a_name_the_user_told_us_survives_a_model_that_drops_it(client, users, use_llm):
    use_llm(make_fake_llm(memories_json='["Works at Infosys"]'))
    conversation_id = chat(users[0])
    ask(client, users[0], "myself dishant kumar", conversation_id)                 # remembered instantly
    ask(client, users[0], "I joined Infosys last month. How many vacation days do I get?", conversation_id)

    remember(client, users[0], conversation_id)

    assert sorted(m.text for m in store.list_memories(users[0].id)) == ["Name: Dishant Kumar", "Works at Infosys"]


def test_remember_is_only_for_your_own_chats(client, users, use_llm):
    use_llm(make_fake_llm())
    alices = chat(users[0])
    assert remember(client, users[1], alices).status_code == 404
    assert remember(client, users[0], "00000000-0000-4000-8000-000000000000").status_code == 404
    assert client.post(f"/conversations/{alices}/remember").status_code == 401


@pytest.mark.parametrize("model_output", ['["x"', "[]"])
def test_an_unusable_or_empty_answer_never_wipes_the_memory(client, users, use_llm, model_output):
    use_llm(make_fake_llm(memories_json=model_output))
    store.add_memory(users[0].id, "Prefers short answers")
    conversation_id = chat(users[0])
    ask(client, users[0], "How many vacation days do employees get?", conversation_id)
    remember(client, users[0], conversation_id)
    assert [m.text for m in store.list_memories(users[0].id)] == ["Prefers short answers"]


def test_what_the_user_said_counts_even_when_the_chat_had_no_documents(client, users, use_llm):
    """The answer was "add a document first", but the user's own words are still worth remembering."""
    from app.services.conversations import create_conversation
    from app.db.database import SessionLocal

    calls = []
    use_llm(make_fake_llm(calls=calls, memories_json='["Is rolling out the new leave policy"]'))
    with SessionLocal() as session:
        conversation_id = str(create_conversation(session, users[0].id).id)      # a chat WITHOUT documents (its public id)
    ask(client, users[0], "I am rolling out the new leave policy next month, what should I check?", conversation_id)

    remember(client, users[0], conversation_id)

    [prompt] = memory_calls(calls)
    assert "rolling out the new leave policy" in prompt and "add a document" not in prompt.lower().split("the recent conversation:")[1]
    assert [m.text for m in store.list_memories(users[0].id)] == ["Is rolling out the new leave policy"]
