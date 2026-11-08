"""
POST /ask/stream: the answer arrives as Server-Sent Events while the model writes it.

Same real app, Postgres test DB, Qdrant test collection and models as test_retrieve_ask_api.py;
only the LLM is fake. The fake here yields the answer word by word, so the stream really has
several token events (the plain fake in conftest returns the whole answer in one piece).
"""

import json

import pytest

from langchain_core.runnables import RunnableGenerator

from app.db.models import Conversation, Message, User
from app.generation.llm import get_llm
from tests.conftest import auth_header, conversation_pk, make_fake_llm, make_token, unique_clerk_id
from tests.conftest import chat_with_documents
from tests.test_retrieve_ask_api import chat, headers_for, use_llm, users  # noqa: F401  (shared fixtures)

QUESTION = "How many vacation days do employees get?"


def make_streaming_llm(answer="Employees get twenty days of paid vacation [1].", fail_after=None):
    """
    A fake chat model that yields the answer one word at a time. Other pipeline steps
    (query paraphrases, rewriting, summaries) get a short non-streamed reply.
    With fail_after=N the answer step raises after N words (a model that breaks halfway).
    """

    def fake(prompt_values):
        for prompt_value in prompt_values:
            text = prompt_value.to_string()
            if "different phrasings" in text:
                yield ""
            elif "Standalone query" in text:
                yield "rewritten question"
            elif "running summary of a conversation" in text:
                yield "SUMMARY"
            elif "You maintain the long-term memory" in text:
                yield "[]"
            else:
                words = answer.split(" ")
                for number, word in enumerate(words):
                    if fail_after is not None and number >= fail_after:
                        raise RuntimeError("provider exploded halfway")
                    yield word + (" " if number < len(words) - 1 else "")

    return RunnableGenerator(fake)


def parse_events(text: str) -> list[tuple[str, dict]]:
    """'event: x\\ndata: {...}\\n\\n' blocks -> [("x", {...}), ...]"""
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def stream(client, user, **payload):
    """Streams QUESTION; without a conversation_id it asks into a new chat holding the user's corpus documents."""
    payload.setdefault("conversation_id", chat(user))
    return client.post("/ask/stream", headers=headers_for(user), json={"query": QUESTION, **payload})


def test_stream_requires_auth(client):
    assert client.post("/ask/stream", json={"query": QUESTION}).status_code == 401


def test_stream_without_configured_llm_is_503(client, users):
    assert stream(client, users[0]).status_code == 503


def test_stream_sends_tokens_then_done_and_saves_the_turn(client, users, use_llm, db):
    use_llm(make_streaming_llm())
    resp = stream(client, users[0])

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_events(resp.text)

    kinds = [kind for kind, _ in events]
    assert kinds[-1] == "done" and kinds.count("done") == 1
    assert kinds.count("token") > 1                                  # really streamed, not one blob
    streamed = "".join(data["text"] for kind, data in events if kind == "token")
    done = events[-1][1]
    assert streamed == done["answer"] == "Employees get twenty days of paid vacation [1]."
    assert done["abstained"] is False and done["citations"][0]["marker"] == "[1]"
    assert {"conversation_id", "message_id", "created_at"} <= set(done)

    messages = db.query(Message).filter_by(conversation_id=conversation_pk(done["conversation_id"])).order_by(Message.id).all()
    assert [(m.role, m.content) for m in messages] == [("user", QUESTION), ("assistant", done["answer"])]
    assert messages[1].id == done["message_id"]


def test_stream_done_matches_the_json_endpoint(client, users, use_llm):
    use_llm(make_streaming_llm("See twenty days [1] and more [2]."))
    json_body = client.post("/ask", headers=headers_for(users[0]), json={"query": QUESTION, "conversation_id": chat(users[0])}).json()
    done = parse_events(stream(client, users[0]).text)[-1][1]

    for key in ("answer", "abstained", "citations"):
        assert done[key] == json_body[key]


def test_stream_continues_an_existing_conversation(client, users, use_llm, db):
    use_llm(make_streaming_llm())
    first = parse_events(stream(client, users[0]).text)[-1][1]
    second = parse_events(stream(client, users[0], conversation_id=first["conversation_id"]).text)[-1][1]

    assert second["conversation_id"] == first["conversation_id"]
    assert db.query(Message).filter_by(conversation_id=conversation_pk(first["conversation_id"])).count() == 4


def test_stream_unknown_or_foreign_conversation_is_a_real_404(client, users, use_llm, db):
    use_llm(make_streaming_llm())
    alice, bob = users
    conversation_id = parse_events(stream(client, alice).text)[-1][1]["conversation_id"]

    resp = stream(client, bob, conversation_id=conversation_id)
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")      # an HTTP error, not a stream
    assert db.query(Message).filter_by(conversation_id=conversation_pk(conversation_id)).count() == 2

    assert stream(client, alice, conversation_id="00000000-0000-4000-8000-000000000000").status_code == 404


def test_stream_model_refusal_replaces_the_preview_and_has_no_citations(client, users, use_llm):
    use_llm(make_streaming_llm("I don't have enough information to answer that."))
    events = parse_events(stream(client, users[0]).text)

    done = events[-1][1]
    assert done["abstained"] is True and done["citations"] == []


def test_stream_nothing_found_refuses_without_calling_the_answer_prompt(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(calls=calls))
    stranger = User(clerk_user_id=unique_clerk_id(), email="c@example.com")
    db.add(stranger)
    db.commit()

    # a chat whose only document has no indexed text: the search finds nothing
    events = parse_events(stream(client, stranger, conversation_id=chat_with_documents(stranger.id, [999])).text)

    assert [kind for kind, _ in events] == ["token", "done"]
    assert events[-1][1]["abstained"] is True and events[-1][1]["answer"].startswith("I don't have enough information")
    assert not any("Context:" in prompt for prompt in calls)


def test_stream_llm_failure_before_the_first_token_is_502_and_saves_nothing(client, users, use_llm, db):
    use_llm(make_streaming_llm(fail_after=0))
    resp = stream(client, users[0])

    assert resp.status_code == 502
    assert "exploded" not in resp.text
    assert db.query(Message).count() == 0     # the chat made by stream() exists, but nothing was saved into it


def test_stream_quota_error_is_429_with_a_friendly_message(client, users, use_llm, db):
    from langchain_core.runnables import RunnableLambda

    def quota(prompt_value):
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded for key AIza-secret-123")

    use_llm(RunnableLambda(quota))
    resp = stream(client, users[0])

    assert resp.status_code == 429 and "try again later" in resp.json()["detail"]
    assert "AIza-secret-123" not in resp.text
    assert db.query(Message).count() == 0     # the chat made by stream() exists, but nothing was saved into it


def test_stream_failure_halfway_sends_an_error_event_and_saves_nothing(client, users, use_llm, db):
    use_llm(make_streaming_llm(fail_after=3))
    resp = stream(client, users[0])

    assert resp.status_code == 200                                    # headers were already sent
    events = parse_events(resp.text)
    kinds = [kind for kind, _ in events]
    assert kinds[-1] == "error" and "done" not in kinds and kinds.count("token") >= 1
    assert events[-1][1]["status"] == 502
    assert "exploded" not in resp.text
    assert db.query(Message).count() == 0     # the chat made by stream() exists, but nothing was saved into it


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "x" * 4001}, {}])
def test_stream_validates_input(client, users, use_llm, payload):
    use_llm(make_streaming_llm())
    assert client.post("/ask/stream", headers=headers_for(users[0]), json=payload).status_code == 422


def test_stream_without_documents_sends_the_fixed_reply_as_one_token(client, users, use_llm):
    from app.services.small_talk import NEED_DOCUMENT_REPLY

    calls = []
    use_llm(make_fake_llm(calls=calls))
    events = parse_events(stream(client, users[0], conversation_id=chat_with_documents(users[0].id, [])).text)
    assert events == [("token", {"text": NEED_DOCUMENT_REPLY}), ("done", events[-1][1])]
    assert events[-1][1]["answer"] == NEED_DOCUMENT_REPLY and calls == []
