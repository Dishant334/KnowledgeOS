"""
POST /retrieve and POST /ask on the REAL app (app.main).

Real: FastAPI + auth dependency (RS256 test tokens, fake JWKS), Postgres test DB,
Qdrant test collection, embedding + reranker models.
Fake: the LLM (dependency override) — no LLM provider exists yet.
Mocked in a few failure tests: the retrieval call itself.

Users are created in order so their ids are 1 and 2, matching the
`uploaded_by` values in the shared corpus (tests/conftest.py).
"""

import pytest

from app.db.models import Conversation, Message, User
from app.generation.llm import get_llm
from tests.conftest import CORPUS_DOCUMENTS, auth_header, chat_with_documents, make_fake_llm, make_token, unique_clerk_id


@pytest.fixture
def users(db, retrieval_corpus):
    """Two users with ids 1 and 2 (tables are reset after every test)."""
    created = []
    for name in ("alice", "bob"):
        user = User(clerk_user_id=unique_clerk_id(), email=f"{name}@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
        created.append(user)
    assert [u.id for u in created] == [1, 2]
    return created


def headers_for(user):
    return auth_header(make_token(user.clerk_user_id))


def chat(user):
    """A new conversation of the user with their corpus documents attached (questions only search those)."""
    return chat_with_documents(user.id, CORPUS_DOCUMENTS.get(user.id, []))


@pytest.fixture
def use_llm(app):
    """use_llm(fake_llm) installs a fake model for /retrieve and /ask."""

    def install(llm):
        app.dependency_overrides[get_llm] = lambda: llm

    yield install
    app.dependency_overrides.pop(get_llm, None)


# --- /retrieve ------------------------------------------------------------------------------


def test_retrieve_requires_auth(client):
    assert client.post("/retrieve", json={"query": "vacation"}).status_code == 401


def test_retrieve_returns_ranked_chunks_with_stage_scores(client, users):
    resp = client.post("/retrieve", headers=headers_for(users[0]),
                       json={"query": "How many vacation days do employees get?", "top_k": 3})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["query"] == "How many vacation days do employees get?"
    assert body["took_ms"] > 0
    results = body["results"]
    assert 1 <= len(results) <= 3
    assert "twenty days of paid vacation" in results[0]["chunk_text"]
    assert results[0]["document_id"] == 10 and results[0]["source_name"] == "handbook.pdf"
    assert results[0]["page_number"] == 1
    assert results[0]["fused_score"] is not None and results[0]["rerank_score"] is not None
    assert results[0]["score"] == results[0]["rerank_score"]
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert len({r["chunk_id"] for r in results}) == len(results)


def test_retrieve_only_returns_the_callers_documents(client, users):
    alice, bob = users
    query = {"query": "Berlin office vacation days", "top_k": 10}

    alice_results = client.post("/retrieve", headers=headers_for(alice), json=query).json()["results"]
    bob_results = client.post("/retrieve", headers=headers_for(bob), json=query).json()["results"]

    assert {r["document_id"] for r in alice_results} <= {10, 11}
    assert {r["document_id"] for r in bob_results} == {20}
    assert all("Berlin" not in r["chunk_text"] for r in alice_results)


def test_retrieve_document_ids_and_doc_type_narrow_results(client, users):
    alice, _ = users
    only_doc_11 = client.post("/retrieve", headers=headers_for(alice),
                              json={"query": "work", "document_ids": [11]}).json()["results"]
    assert {r["document_id"] for r in only_doc_11} == {11}

    md_only = client.post("/retrieve", headers=headers_for(alice),
                          json={"query": "work policy", "doc_type": "md", "top_k": 10}).json()["results"]
    assert md_only and {r["document_id"] for r in md_only} == {11}

    foreign_doc = client.post("/retrieve", headers=headers_for(alice),
                              json={"query": "vacation", "document_ids": [20]}).json()["results"]
    assert foreign_doc == []   # document 20 is Bob's


def test_retrieve_with_no_documents_is_empty_not_an_error(client, users, db):
    stranger = User(clerk_user_id=unique_clerk_id(), email="c@example.com")
    db.add(stranger)
    db.commit()
    resp = client.post("/retrieve", headers=headers_for(stranger), json={"query": "vacation"})
    assert resp.status_code == 200 and resp.json()["results"] == []


def test_retrieve_with_llm_still_works(client, users, use_llm):
    use_llm(make_fake_llm(variants=["paid vacation days"]))
    resp = client.post("/retrieve", headers=headers_for(users[0]), json={"query": "vacation days"})
    assert resp.status_code == 200
    assert "twenty days" in resp.json()["results"][0]["chunk_text"]


@pytest.mark.parametrize("payload", [
    {"query": ""},
    {"query": "x", "top_k": 0},
    {"query": "x", "top_k": 51},
    {"query": "x" * 2001},
    {"query": "x", "document_ids": "10"},
])
def test_retrieve_validates_input(client, users, payload):
    assert client.post("/retrieve", headers=headers_for(users[0]), json=payload).status_code == 422


def test_retrieve_returns_503_when_qdrant_is_unavailable(client, users, monkeypatch):
    import app.services.retrieve as service

    def down(*args, **kwargs):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(service, "retrieve", down)
    resp = client.post("/retrieve", headers=headers_for(users[0]), json={"query": "vacation"})
    assert resp.status_code == 503
    assert "qdrant" not in resp.text.lower()   # no internal details leaked


# --- /ask ----------------------------------------------------------------------------------------


def test_ask_requires_auth(client):
    assert client.post("/ask", json={"query": "vacation"}).status_code == 401


def test_ask_without_configured_llm_is_503(client, users):
    resp = client.post("/ask", headers=headers_for(users[0]), json={"query": "How many vacation days?"})
    assert resp.status_code == 503
    assert "LLM" in resp.json()["detail"]


def test_ask_answers_with_citations_and_saves_the_turn(client, users, use_llm, db):
    use_llm(make_fake_llm(answer="Employees get twenty days of paid vacation [1]."))
    resp = client.post("/ask", headers=headers_for(users[0]), json={"query": "How many vacation days do employees get?", "conversation_id": chat(users[0])})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["answer"] == "Employees get twenty days of paid vacation [1]."
    assert body["abstained"] is False
    first = body["citations"][0]
    assert first["marker"] == "[1]" and first["document_id"] == 10
    assert first["source_name"] == "handbook.pdf" and first["page_number"] == 1
    assert {c["document_id"] for c in body["citations"]} <= {10, 11}   # only Alice's documents

    messages = db.query(Message).filter_by(conversation_id=body["conversation_id"]).order_by(Message.id).all()
    assert [(m.role, m.content) for m in messages] == [
        ("user", "How many vacation days do employees get?"),
        ("assistant", body["answer"]),
    ]
    assert messages[1].id == body["message_id"]


def test_ask_follow_up_uses_conversation_history(client, users, use_llm):
    calls = []
    use_llm(make_fake_llm(answer="Twenty days [1].", rewritten="How many vacation days do employees get?", calls=calls))
    headers = headers_for(users[0])

    first = client.post("/ask", headers=headers, json={"query": "How many vacation days do employees get?",
                                                      "conversation_id": chat(users[0])}).json()
    calls.clear()
    second = client.post("/ask", headers=headers,
                         json={"query": "and in total per month?", "conversation_id": first["conversation_id"]})

    assert second.status_code == 200, second.text
    assert second.json()["conversation_id"] == first["conversation_id"]
    rewrite_prompts = [c for c in calls if "Standalone query" in c]
    assert rewrite_prompts and "How many vacation days do employees get?" in rewrite_prompts[0]
    answer_prompts = [c for c in calls if "Context:" in c and "Standalone query" not in c]
    assert "Human: How many vacation days do employees get?" in answer_prompts[0]   # history reached the answer prompt


def test_ask_abstains_without_calling_the_llm_when_nothing_is_found(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(calls=calls))
    stranger = User(clerk_user_id=unique_clerk_id(), email="c@example.com")
    db.add(stranger)
    db.commit()
    empty_chat = chat_with_documents(stranger.id, [999])     # a document with no indexed text: the search finds nothing

    resp = client.post("/ask", headers=headers_for(stranger), json={"query": "How many vacation days?", "conversation_id": empty_chat})

    assert resp.status_code == 200
    body = resp.json()
    assert body["abstained"] is True and body["citations"] == []
    assert body["answer"].startswith("I don't have enough information")
    # retrieval may still ask the LLM for query paraphrases, but the answer prompt
    # (the one that contains the retrieved "Context:") must never be sent
    assert not any("Context:" in prompt for prompt in calls)


def test_ask_abstention_from_the_model_has_no_citations(client, users, use_llm):
    use_llm(make_fake_llm(answer="I don't have enough information to answer that."))
    body = client.post("/ask", headers=headers_for(users[0]),
                       json={"query": "What is the CEO's salary?", "conversation_id": chat(users[0])}).json()
    assert body["abstained"] is True and body["citations"] == []


def test_ask_cannot_use_another_users_conversation(client, users, use_llm, db):
    use_llm(make_fake_llm())
    alice, bob = users
    conversation_id = client.post("/ask", headers=headers_for(alice),
                                  json={"query": "vacation days?", "conversation_id": chat(alice)}).json()["conversation_id"]

    resp = client.post("/ask", headers=headers_for(bob),
                       json={"query": "vacation days?", "conversation_id": conversation_id})
    assert resp.status_code == 404
    assert db.query(Message).filter_by(conversation_id=conversation_id).count() == 2   # unchanged


def test_ask_never_cites_other_users_documents(client, users, use_llm):
    use_llm(make_fake_llm(answer="See [1] and [2]."))
    body = client.post("/ask", headers=headers_for(users[1]),
                       json={"query": "vacation salary Berlin", "conversation_id": chat(users[1])}).json()
    assert {c["document_id"] for c in body["citations"]} == {20}


def test_ask_llm_failure_is_502_and_saves_nothing(client, users, use_llm, db):
    from langchain_core.runnables import RunnableLambda

    def fail(prompt_value):
        raise RuntimeError("provider exploded")

    use_llm(RunnableLambda(fail))
    resp = client.post("/ask", headers=headers_for(users[0]), json={"query": "How many vacation days?", "conversation_id": chat(users[0])})

    assert resp.status_code == 502
    assert "exploded" not in resp.text
    assert db.query(Conversation).count() == 1 and db.query(Message).count() == 0     # only the chat made above


def test_ask_quota_exhausted_is_429_with_a_friendly_message(client, users, use_llm, db):
    from langchain_core.runnables import RunnableLambda

    def quota(prompt_value):
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded for key AIza-secret-123")

    use_llm(RunnableLambda(quota))
    resp = client.post("/ask", headers=headers_for(users[0]), json={"query": "How many vacation days?", "conversation_id": chat(users[0])})

    assert resp.status_code == 429
    assert "try again later" in resp.json()["detail"]
    assert "AIza-secret-123" not in resp.text            # provider error text never reaches the client
    assert db.query(Message).count() == 0


def test_ask_uses_the_local_fallback_when_the_cloud_model_fails(client, users, use_llm):
    """Same wiring get_llm() builds: primary.with_fallbacks([fallback])."""
    from langchain_core.runnables import RunnableLambda

    def cloud_down(prompt_value):
        raise RuntimeError("429 quota exceeded")

    local = make_fake_llm(answer="Employees get twenty days of paid vacation [1].")
    use_llm(RunnableLambda(cloud_down).with_fallbacks([local]))

    resp = client.post("/ask", headers=headers_for(users[0]),
                       json={"query": "How many vacation days do employees get?", "conversation_id": chat(users[0])})

    assert resp.status_code == 200, resp.text
    assert resp.json()["answer"] == "Employees get twenty days of paid vacation [1]."
    assert resp.json()["citations"][0]["marker"] == "[1]"


def test_ask_qdrant_outage_is_503_and_saves_nothing(client, users, use_llm, db, monkeypatch):
    import app.services.retrieve as service

    use_llm(make_fake_llm())

    def down(*args, **kwargs):
        raise ConnectionError("qdrant down")

    monkeypatch.setattr(service, "retrieve", down)
    resp = client.post("/ask", headers=headers_for(users[0]), json={"query": "vacation?", "conversation_id": chat(users[0])})

    assert resp.status_code == 503
    assert db.query(Message).count() == 0


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "x" * 4001}, {"query": "x", "conversation_id": "abc"}])
def test_ask_validates_input(client, users, use_llm, payload):
    use_llm(make_fake_llm())
    assert client.post("/ask", headers=headers_for(users[0]), json=payload).status_code == 422


# --- /ask with the REAL local model (Qwen3 8B via Ollama); skipped if it is not available -------------------


def test_ask_end_to_end_with_real_qwen(client, users, use_llm):
    from app.generation.llm import build_llm
    from tests.test_llm import ollama_has_model

    if not ollama_has_model():
        pytest.skip("Ollama or the model is not available")
    use_llm(build_llm("ollama"))
    headers = headers_for(users[0])
    conversation_id = chat(users[0])

    answer = client.post("/ask", headers=headers, json={"query": "How many vacation days do employees get?", "conversation_id": conversation_id})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert "twenty" in body["answer"].lower() or "20" in body["answer"]
    assert "[1]" in body["answer"] and "<think>" not in body["answer"]
    assert body["citations"][0]["document_id"] == 10 and body["abstained"] is False

    refusal = client.post("/ask", headers=headers, json={"query": "What is the CEO's salary?", "conversation_id": conversation_id}).json()
    assert refusal["abstained"] is True and refusal["citations"] == []


def test_ask_multi_turn_conversation_with_real_qwen(client, users, use_llm, db):
    """Two turns in one conversation as Bob (owner of the Berlin document): real retrieval + real Qwen."""
    from app.generation.llm import build_llm
    from tests.test_llm import ollama_has_model

    if not ollama_has_model():
        pytest.skip("Ollama or the model is not available")
    use_llm(build_llm("ollama"))
    headers = headers_for(users[1])

    first = client.post("/ask", headers=headers, json={"query": "How many vacation days do Berlin employees get?",
                                                      "conversation_id": chat(users[1])}).json()
    assert "thirty" in first["answer"].lower() or "30" in first["answer"]
    assert {c["document_id"] for c in first["citations"]} == {20}

    second = client.post("/ask", headers=headers, json={
        "query": "And how often are the salary bands there reviewed?", "conversation_id": first["conversation_id"]})
    assert second.status_code == 200, second.text
    assert second.json()["conversation_id"] == first["conversation_id"]
    assert "january" in second.json()["answer"].lower()

    saved = db.query(Message).filter_by(conversation_id=first["conversation_id"]).order_by(Message.id).all()
    assert [m.role for m in saved] == ["user", "assistant", "user", "assistant"]


# --- documents belong to conversations ------------------------------------------------------------------------


def test_a_question_only_searches_the_documents_of_its_own_conversation(client, users, use_llm):
    use_llm(make_fake_llm(answer="See [1] and [2]."))
    alice = users[0]
    only_remote = chat_with_documents(alice.id, [11])          # Alice owns 10 and 11; this chat has only 11
    body = client.post("/ask", headers=headers_for(alice),
                       json={"query": "How many vacation days do employees get?", "conversation_id": only_remote}).json()
    assert {c["document_id"] for c in body["citations"]} <= {11}
    assert 10 not in {c["document_id"] for c in body["citations"]}


@pytest.mark.parametrize("conversation", ["none", "empty chat"])
def test_without_documents_a_real_question_asks_for_a_document_and_never_searches_or_calls_the_llm(
        client, users, use_llm, db, monkeypatch, conversation):
    import app.services.retrieve as service
    from app.services.small_talk import NEED_DOCUMENT_REPLY

    calls = []
    use_llm(make_fake_llm(calls=calls))
    monkeypatch.setattr(service, "retrieve", lambda *a, **k: pytest.fail("no search without documents"))
    payload = {"query": "How many vacation days do employees get?"}
    if conversation == "empty chat":
        payload["conversation_id"] = chat_with_documents(users[0].id, [])

    body = client.post("/ask", headers=headers_for(users[0]), json=payload).json()

    assert body["answer"] == NEED_DOCUMENT_REPLY and body["abstained"] is True and body["citations"] == []
    assert calls == []                                               # no LLM call at all
    saved = db.query(Message).filter_by(conversation_id=body["conversation_id"]).order_by(Message.id).all()
    assert [m.role for m in saved] == ["user", "assistant"]          # still a normal, saved turn


@pytest.mark.parametrize("greeting", ["hi", "Hello!", "hey there", "good morning", "thanks", "who are you?"])
def test_without_documents_small_talk_gets_a_hello(client, users, use_llm, greeting):
    from app.services.small_talk import GREETING_REPLY

    calls = []
    use_llm(make_fake_llm(calls=calls))
    body = client.post("/ask", headers=headers_for(users[0]), json={"query": greeting}).json()
    assert body["answer"] == GREETING_REPLY and body["abstained"] is False and calls == []


def test_small_talk_detection():
    from app.services.small_talk import is_small_talk

    for text in ["hi", "HI!!", "hii", "hello there", "Hey", "good evening", "thank you so much", "how are you?", "ok", "help"]:
        assert is_small_talk(text), text
    for text in ["hi, how many vacation days do I get?", "what is the leave policy", "hello world program in python",
                 "summarise the report", "", "thanks for the budget numbers, what about Q3?"]:
        assert not is_small_talk(text), text
