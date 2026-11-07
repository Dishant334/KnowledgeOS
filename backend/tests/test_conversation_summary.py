"""
Conversation memory: old messages are summarized and stored, never dropped.

  1. UNIT         split / summarize / prompt block (fake model)
  2. API + DB     real Postgres, real Qdrant + models for retrieval, FAKE LLM
  3. REAL QWEN    local Qwen3 8B writes the summary (auto-skipped if Ollama is missing)
"""

import pytest
from langchain_core.runnables import RunnableLambda

from app.db.models import Conversation, Message
from app.generation.chain import build_generation_chain
from app.generation.orchestrator import (
    HISTORY_MAX_TOKENS,
    RECENT_KEEP_TOKENS,
    count_tokens,
    summary_block,
)
from app.generation.summary import SUMMARY_MAX_WORDS, format_messages, split_for_summary, summarize
from app.services.ask import _history_as_text
from tests.conftest import CORPUS_DOCUMENTS, attach_documents, make_fake_llm
from tests.test_llm import needs_ollama
# fixtures used below (users, use_llm) and helper
from tests.test_retrieve_ask_api import headers_for, use_llm, users  # noqa: F401

SUMMARY_TEXT = "The user asked about leave rules; the assistant said employees get twenty days."


def words(label: str, n: int = 400) -> str:
    """A message of roughly n tokens that starts with a recognisable label."""
    return f"{label} " + "word " * n


# --- 1. unit -------------------------------------------------------------------------------------


def test_split_keeps_the_newest_tail_that_fits_and_starts_with_a_user_message():
    msgs = [(1, "user", words("a", 400)), (2, "assistant", words("b", 400)),
            (3, "user", "short question"), (4, "assistant", "short answer")]
    old, recent = split_for_summary(msgs, keep_tokens=100)
    assert [m[0] for m in recent] == [3, 4] and [m[0] for m in old] == [1, 2]


def test_split_never_starts_the_recent_part_with_the_assistant():
    msgs = [(1, "user", "q1"), (2, "assistant", "a1"), (3, "user", words("big", 300)), (4, "assistant", "a2")]
    old, recent = split_for_summary(msgs, keep_tokens=count_tokens("a2") + 5)
    assert recent == []                                  # 'a2' alone cannot start the history
    assert [m[0] for m in old] == [1, 2, 3, 4]


def test_split_with_nothing_to_summarize():
    assert split_for_summary([], 100) == ([], [])
    msgs = [(1, "user", "hi"), (2, "assistant", "hello")]
    assert split_for_summary(msgs, keep_tokens=1000) == ([], msgs)


def test_summarize_sends_previous_summary_and_new_messages():
    seen = []
    llm = RunnableLambda(lambda pv: seen.append(pv.to_string()) or "  New summary text.  ")
    result = summarize(llm, "Earlier: user asked about Berlin.", [("user", "How many days?"), ("assistant", "Thirty.")])
    assert result == "New summary text."
    prompt = seen[0]
    assert "Earlier: user asked about Berlin." in prompt
    assert "User: How many days?" in prompt and "Assistant: Thirty." in prompt
    assert f"at most {SUMMARY_MAX_WORDS} words" in prompt


def test_summarize_first_time_says_there_is_no_summary_yet():
    seen = []
    summarize(RunnableLambda(lambda pv: seen.append(pv.to_string()) or "ok"), "", [("user", "hi")])
    assert "(none yet)" in seen[0]


def test_summarize_rejects_an_empty_result_so_the_old_summary_is_kept():
    with pytest.raises(ValueError):
        summarize(RunnableLambda(lambda pv: "   "), "old", [("user", "hi")])


def test_summary_block_text():
    assert summary_block("") == "" and summary_block("   ") == ""
    block = summary_block("User likes Berlin.")
    assert "User likes Berlin." in block and "do not cite it" in block and block.endswith("\n\n")


def test_answer_prompt_contains_the_summary_only_when_there_is_one():
    seen = []
    llm = RunnableLambda(lambda pv: seen.append(pv.to_messages()) or "ok")
    chain = build_generation_chain(llm)
    chain.invoke({"context": "[1] fact", "question": "q", "history": []})
    chain.invoke({"context": "[1] fact", "question": "q", "history": [], "summary_block": summary_block("SUM")})
    without, with_summary = seen[0][0].content, seen[1][0].content
    assert "Summary of the earlier conversation" not in without
    assert "SUM" in with_summary and with_summary.index("SUM") < with_summary.index("Context:")


def test_rewriter_history_text_includes_summary_then_recent_messages():
    text = _history_as_text("User works in Berlin.", [("user", "q"), ("assistant", "a")])
    assert text == "Summary of the earlier conversation: User works in Berlin.\nUser: q\nAssistant: a"
    assert _history_as_text("", []) == ""
    assert _history_as_text("", [("user", "q")]) == "User: q"


def test_format_messages():
    assert format_messages([("user", "a"), ("assistant", "b")]) == "User: a\nAssistant: b"


# --- 2. API + database (fake LLM) ----------------------------------------------------------------------


def seed(db, user, labels, n=400):
    """A conversation whose messages alternate user/assistant, each about n tokens."""
    conversation = Conversation(user_id=user.id, title="seeded")
    db.add(conversation)
    db.flush()
    for i, label in enumerate(labels):
        db.add(Message(conversation_id=conversation.id, role="user" if i % 2 == 0 else "assistant", content=words(label, n)))
    db.commit()
    return conversation.id


def ask(client, user, text, conversation_id):
    # questions only search the conversation's own documents: attach the user's corpus documents (idempotent)
    attach_documents(conversation_id, user.id, CORPUS_DOCUMENTS[user.id])
    return client.post("/ask", headers=headers_for(user), json={"query": text, "conversation_id": conversation_id})


def stored(db, conversation_id):
    db.expire_all()
    return db.get(Conversation, conversation_id)


def prompts(calls, kind):
    marker = {"answer": "Context:", "summary": "running summary of a conversation"}[kind]
    return [c for c in calls if marker in c and (kind == "summary" or "running summary of a conversation" not in c)]


def test_long_conversation_is_summarized_stored_and_nothing_is_deleted(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(answer="Twenty days [1].", summary=SUMMARY_TEXT, calls=calls))
    cid = seed(db, users[0], [f"OLD{i}" for i in range(6)])               # ~2400 tokens of earlier chat

    resp = ask(client, users[0], "How many vacation days do employees get?", cid)
    assert resp.status_code == 200, resp.text

    conversation = stored(db, cid)
    messages = db.query(Message).filter_by(conversation_id=cid).order_by(Message.id).all()
    assert len(messages) == 8                                              # 6 seeded + the new question and answer: none deleted
    assert conversation.summary == SUMMARY_TEXT
    assert conversation.summarized_until_message_id == messages[5].id      # the six old messages are covered
    # the summarizer was given the old messages, and ran AFTER the answer (the user did not wait for it)
    summary_call = prompts(calls, "summary")[0]
    assert all(f"OLD{i}" in summary_call for i in range(6))
    assert calls.index(prompts(calls, "answer")[0]) < calls.index(summary_call)


def test_next_question_sends_summary_plus_recent_messages_instead_of_old_text(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(answer="Twenty days [1].", summary=SUMMARY_TEXT, calls=calls))
    cid = seed(db, users[0], [f"OLD{i}" for i in range(6)])
    ask(client, users[0], "How many vacation days do employees get?", cid)
    calls.clear()

    resp = ask(client, users[0], "And how are they paid?", cid)

    assert resp.status_code == 200
    answer_prompt = prompts(calls, "answer")[0]
    assert SUMMARY_TEXT in answer_prompt
    assert "OLD0" not in answer_prompt and "OLD5" not in answer_prompt     # raw old text replaced by the summary
    assert "How many vacation days do employees get?" in answer_prompt     # the recent turn is still sent as it was
    rewrite_prompt = next(c for c in calls if "Standalone query" in c)
    assert f"Summary of the earlier conversation: {SUMMARY_TEXT}" in rewrite_prompt   # follow-ups are rewritten with it


def test_short_conversation_is_not_summarized(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(summary=SUMMARY_TEXT, calls=calls))
    cid = seed(db, users[0], ["a", "b"], n=20)

    assert ask(client, users[0], "How many vacation days?", cid).status_code == 200

    assert prompts(calls, "summary") == []
    conversation = stored(db, cid)
    assert conversation.summary is None and conversation.summarized_until_message_id is None


def test_summary_is_rolling_the_previous_summary_goes_into_the_next_one(client, users, use_llm, db):
    calls = []
    use_llm(make_fake_llm(answer="Twenty days [1].", summary="FIRST SUMMARY", calls=calls))
    cid = seed(db, users[0], [f"OLD{i}" for i in range(6)])
    ask(client, users[0], "How many vacation days do employees get?", cid)
    first_marker = stored(db, cid).summarized_until_message_id

    for i, label in enumerate(["MID0", "MID1", "MID2", "MID3"]):           # the chat goes on and gets long again
        db.add(Message(conversation_id=cid, role="user" if i % 2 == 0 else "assistant", content=words(label)))
    db.commit()
    calls.clear()
    ask(client, users[0], "Anything else?", cid)

    second_summary_prompt = prompts(calls, "summary")[0]
    assert "FIRST SUMMARY" in second_summary_prompt                        # the old summary is carried forward
    assert "MID0" in second_summary_prompt and "OLD0" not in second_summary_prompt
    assert stored(db, cid).summarized_until_message_id > first_marker


def test_failed_summary_never_fails_the_request_and_is_retried_next_time(client, users, use_llm, db):
    calls = []
    fine = make_fake_llm(answer="Twenty days [1].", summary=SUMMARY_TEXT, calls=calls)
    broken = {"on": True}

    def run(prompt_value):
        if broken["on"] and "running summary of a conversation" in prompt_value.to_string():
            raise RuntimeError("summary model is down")
        return fine.invoke(prompt_value)

    use_llm(RunnableLambda(run))
    cid = seed(db, users[0], [f"OLD{i}" for i in range(6)])

    first = ask(client, users[0], "How many vacation days do employees get?", cid)
    assert first.status_code == 200 and first.json()["answer"] == "Twenty days [1]."
    assert stored(db, cid).summary is None                                  # nothing half-written
    assert db.query(Message).filter_by(conversation_id=cid).count() == 8    # and no message lost

    broken["on"] = False
    assert ask(client, users[0], "And how are they paid?", cid).status_code == 200
    assert stored(db, cid).summary == SUMMARY_TEXT                          # retried and caught up


def test_the_prompt_stays_inside_the_window_even_if_summarizing_keeps_failing(client, users, use_llm, db):
    seen = []

    def run(prompt_value):
        text = prompt_value.to_string()
        seen.append(text)
        if "running summary of a conversation" in text:
            raise RuntimeError("down")
        return "Twenty days [1]."

    use_llm(RunnableLambda(run))
    cid = seed(db, users[0], [f"OLD{i}" for i in range(14)])               # ~5600 tokens, no summary possible

    assert ask(client, users[0], "How many vacation days do employees get?", cid).status_code == 200

    answer_prompt = next(t for t in seen if "Context:" in t and "running summary" not in t)
    assert count_tokens(answer_prompt) < 8192 - 1500                       # the last-resort trim keeps room for the answer
    assert "OLD13" in answer_prompt and "OLD0" not in answer_prompt        # newest kept, oldest cut by the safety net


def test_each_user_only_gets_their_own_conversation_summary(client, users, use_llm, db):
    use_llm(make_fake_llm(answer="Twenty days [1].", summary=SUMMARY_TEXT))
    alice, bob = users
    cid = seed(db, alice, [f"OLD{i}" for i in range(6)])
    ask(client, alice, "How many vacation days do employees get?", cid)

    assert ask(client, bob, "What did we talk about?", cid).status_code == 404     # not Bob's conversation


def test_budget_numbers_leave_room_for_context_summary_question_and_answer():
    summary_tokens, context, question, rules, answer_room = 300, 3000, 1000, 200, 1500
    assert HISTORY_MAX_TOKENS + summary_tokens + context + question + rules + answer_room <= 8192
    assert RECENT_KEEP_TOKENS < HISTORY_MAX_TOKENS                          # summarizing frees real space


# --- 3. real local model --------------------------------------------------------------------------------------------


@needs_ollama
def test_real_qwen_writes_a_short_summary_that_keeps_the_key_facts():
    from app.generation.llm import build_llm

    messages = [
        ("user", "Hi, I work in the Berlin office. How many vacation days do I get?"),
        ("assistant", "Employees of the Berlin office receive thirty days of paid vacation per year [1]."),
        ("user", "And when are our salary bands reviewed?"),
        ("assistant", "The salary bands for the Berlin office are reviewed every January [2]."),
    ]
    summary = summarize(build_llm("ollama"), "", messages)

    lowered = summary.lower()
    assert "berlin" in lowered and ("thirty" in lowered or "30" in lowered) and "january" in lowered
    assert len(summary.split()) <= SUMMARY_MAX_WORDS * 1.5
    assert "<think>" not in summary


@needs_ollama
def test_real_qwen_end_to_end_long_conversation(client, users, use_llm, db):
    from app.generation.llm import build_llm

    use_llm(build_llm("ollama"))
    bob = users[1]
    paragraph = ("The Berlin office allows remote work three days per week with manager approval, "
                 "and employees receive thirty days of paid vacation per year. ") * 12
    cid = seed(db, bob, ["x"] * 0)
    for i in range(6):
        db.add(Message(conversation_id=cid, role="user" if i % 2 == 0 else "assistant",
                       content=("Question about Berlin policies. " if i % 2 == 0 else "Answer: ") + paragraph))
    db.commit()

    first = ask(client, bob, "When are the Berlin salary bands reviewed?", cid)
    assert first.status_code == 200, first.text
    assert "january" in first.json()["answer"].lower()

    conversation = stored(db, cid)
    assert conversation.summary and "berlin" in conversation.summary.lower()
    assert count_tokens(conversation.summary) < 400
    assert db.query(Message).filter_by(conversation_id=cid).count() == 8

    second = ask(client, bob, "And how many vacation days do Berlin employees get?", cid)
    assert second.status_code == 200 and ("thirty" in second.json()["answer"].lower() or "30" in second.json()["answer"])
