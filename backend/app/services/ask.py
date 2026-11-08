import logging
from collections.abc import Iterator
from dataclasses import asdict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.tracing import traceable
from app.db.models.conversation import Conversation
from app.db.models.messages import Message
from app.generation.orchestrator import (
    HISTORY_MAX_TOKENS,
    RECENT_KEEP_TOKENS,
    count_tokens,
    generate_answer,
    is_refusal,
    stream_answer,
    trim_history,
)
from app.generation.summary import format_messages, split_for_summary, summarize
from app.memory.consolidate import update_long_term_memory
from app.memory import store as memory_store
from app.memory.store import list_memories
from app.schemas.ask import AskRequest, AskResponse, Citation
from app.services.conversation_memory import remember_if_due
from app.services.conversations import conversation_document_ids
from app.services.introductions import NAME_PREFIX, SelfFact, analyze_message, social_reply
from app.services.retrieve import run_retrieval
from app.services.small_talk import GREETING_REPLY, NEED_DOCUMENT_REPLY, reply_without_documents

logger = logging.getLogger(__name__)


def looks_like_quota_error(error: Exception) -> bool:
    """
    True if an LLM error means "too many requests / free quota used up".
    Every provider SDK raises its own exception type, so we look at the text.
    """
    text = f"{type(error).__name__} {error}".lower()
    words = ("429", "quota", "rate limit", "rate_limit", "ratelimit", "resource_exhausted", "too many requests")
    return any(word in text for word in words)


def _get_conversation(db: Session, user_id: int, conversation_id) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter_by(public_id=conversation_id, user_id=user_id)   # the public UUID from the request
        .first()
    )
    if conversation is None:
        # Also covers another user's conversation id -- treated as
        # not-found rather than leaking a 403, consistent with
        # user-level data isolation.
        raise LookupError("Conversation not found")
    return conversation


def _load_unsummarized(db: Session, conversation: Conversation) -> list[tuple[int, str, str]]:
    """(id, role, content) of the messages NOT yet covered by the summary, oldest first."""
    query = db.query(Message).filter_by(conversation_id=conversation.id)
    if conversation.summarized_until_message_id is not None:
        query = query.filter(Message.id > conversation.summarized_until_message_id)

    return [(m.id, m.role, m.content) for m in query.order_by(Message.id).all()]


def _without_refused_turns(messages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    The history for the model, minus every question that got no real answer (a refusal, or one of the fixed replies
    for a chat without documents) together with that answer. Qwen copies a refusal it sees in the history: a chat
    whose first question came before its PDF was processed kept refusing afterwards (3 of 3 runs, 0 of 2 without the
    history). Nothing is deleted: the chat still shows these turns; they only stay out of the prompt and the rewriter.
    """
    kept: list[tuple[str, str]] = []
    skip_answer = False
    for role, content in messages:
        if role == "user" and analyze_message(content).only_social:
            skip_answer = True                       # a greeting or small talk: neither it nor its reply is useful
            continue
        if role == "assistant" and skip_answer:
            skip_answer = False
            continue
        if role == "assistant" and (content in (GREETING_REPLY, NEED_DOCUMENT_REPLY) or is_refusal(content)):
            if kept and kept[-1][0] == "user":
                kept.pop()           # its question goes too
            continue
        kept.append((role, content))
    return kept


def _remember_self_facts(user_id: int, facts: list[SelfFact], conversation_id: int | None) -> tuple[list[SelfFact], bool]:
    """
    Stores facts the user stated about themselves (see services/introductions.py). A new name replaces the old
    one; a fact already known counts as remembered; text the memory guard refuses is skipped.
    Returns (remembered, memory_full). Never raises: memory problems must not fail /ask.
    """
    remembered: list[SelfFact] = []
    full = False
    try:
        existing = memory_store.list_memories(user_id)
        for fact in facts:
            if memory_store.clean_memory_text(fact.text) is None:
                continue
            if any(m.text.lower() == fact.text.lower() for m in existing):
                remembered.append(fact)                      # already known
                continue
            if fact.kind == "name":
                for old in [m for m in existing if m.text.lower().startswith(NAME_PREFIX.lower())]:
                    memory_store.delete_memory(user_id, old.key)
                    existing.remove(old)
            try:
                existing.append(memory_store.add_memory(user_id, fact.text, conversation_id=conversation_id))
                remembered.append(fact)
            except memory_store.MemoryLimitError:
                full = True
            except ValueError:
                pass                                         # refused by the guard
    except Exception:
        logger.warning("Could not remember what the user said about themselves", exc_info=True)
    return remembered, full


def _load_memories(user_id: int) -> list[str]:
    """
    The long-term facts remembered about this user. Memory is a bonus: if the store
    is unavailable, the question is simply answered without it.
    """
    try:
        return [memory.text for memory in list_memories(user_id)]
    except Exception:
        logger.warning("Could not read long-term memory for user %s; continuing without it", user_id, exc_info=True)
        return []


def _history_as_text(summary: str, history: list[tuple[str, str]], memories: list[str] | None = None) -> str:
    """Plain text of what we know (memory + summary + recent messages) for the query rewriter."""
    parts = []
    if memories:
        parts.append("Known about the user: " + "; ".join(memories))
    if summary:
        parts.append(f"Summary of the earlier conversation: {summary}")
    if history:
        parts.append(format_messages(history))
    return "\n".join(parts)


def _summarize_if_needed(db: Session, conversation: Conversation, llm) -> bool:
    """
    When the messages not yet summarized grow past HISTORY_MAX_TOKENS, fold the
    older ones into conversation.summary and remember how far we got. Nothing is
    deleted: the messages stay in the database, the prompt just stops sending them.

    Runs after the answer is saved. If the model fails, the old summary is kept and
    this is simply tried again after the next question.

    Returns True if the summary was updated.
    """
    messages = _load_unsummarized(db, conversation)
    if sum(count_tokens(content) for _, _, content in messages) <= HISTORY_MAX_TOKENS:
        return False

    old, _recent = split_for_summary(messages, keep_tokens=RECENT_KEEP_TOKENS)
    if not old:
        return False

    try:
        new_summary = summarize(llm, conversation.summary or "", [(role, content) for _, role, content in old])
    except Exception:
        logger.warning("Could not summarize conversation %s; will try again later", conversation.id, exc_info=True)
        return False

    conversation.summary = new_summary
    conversation.summarized_until_message_id = old[-1][0]
    db.commit()
    return True


def _remember_important_facts(user_id: int, conversation: Conversation, llm) -> None:
    """
    Moves what matters from this conversation's summary into the user's long-term
    memory, which every future conversation will see. Never fails the request.
    """
    try:
        update_long_term_memory(llm, user_id, conversation.summary, conversation.id)
    except Exception:
        logger.warning("Could not update long-term memory for user %s", user_id, exc_info=True)


def _save_turn(
    db: Session,
    user_id: int,
    conversation: Conversation | None,
    question: str,
    answer: str,
    citations: list[Citation],
    abstained: bool,
) -> tuple[AskResponse, Conversation]:
    """Saves the question and the answer (creating the conversation if needed): (response, conversation)."""
    if conversation is None:
        conversation = Conversation(user_id=user_id, title=question[:80])
        db.add(conversation)
        db.flush()  # gives the conversation an id

    if conversation.title is None:
        # a chat started with "New chat" has no title yet: the first question names it
        # (a title given at creation, or set by renaming, is never replaced)
        conversation.title = question[:80]

    db.add(Message(conversation_id=conversation.id, role="user", content=question))
    # The citations are saved with the answer (same shape as in the response), so the conversation
    # can be shown again later, source cards included.
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        citations=[citation.model_dump() for citation in citations],
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return AskResponse(
        conversation_id=conversation.public_id,
        message_id=assistant_message.id,
        answer=answer,
        citations=citations,
        abstained=abstained,
        created_at=assistant_message.created_at,
    ), conversation


def ask_stream(db: Session, user_id: int, request: AskRequest, llm) -> Iterator[tuple[str, object]]:
    """
    retrieve -> build cited context -> generate answer -> save the turn, as a stream of events:

        ("token", "text piece") ...   the answer as the model writes it
        ("done", AskResponse)         once, after the turn is saved (the answer in it is the one to trust)

    ONLY the conversation's own documents are searched (conversation_documents). A conversation without documents
    (or a question with no conversation id: a new chat has none yet) gets a fixed reply instead, with no search and
    no LLM call: a hello for small talk, otherwise "add a document to this chat first" (abstained).

    Nothing is saved if retrieval or the LLM fails, so the client can simply retry. Problems are
    raised as before: LookupError (unknown conversation), HTTPException 429 / 502. Before the first
    token they can still become a normal HTTP error; after it the caller reports them in the stream.
    """
    conversation = None
    summary = ""
    history = []
    memories = _load_memories(user_id)
    if request.conversation_id is not None:
        conversation = _get_conversation(db, user_id, request.conversation_id)
        summary = conversation.summary or ""
        unsummarized = [(role, content) for _, role, content in _load_unsummarized(db, conversation)]
        history = trim_history(_without_refused_turns(unsummarized))  # safety net only: normally already small thanks to the summary

    document_ids = conversation_document_ids(db, conversation.id) if conversation is not None else []

    # Greetings, small talk and introductions ("hello, how are you? myself Dishant, what's your name?") get one
    # friendly reply in ANY chat, with no search and no LLM call; self-facts are remembered at once. A message that
    # also asks a real question is answered normally and its self-facts are saved after the turn.
    analysis = analyze_message(request.query)
    self_facts = analysis.facts
    if analysis.only_social:
        if conversation is None:
            conversation = Conversation(user_id=user_id, title=request.query[:80])
            db.add(conversation)
            db.flush()  # gives the conversation an id (committed with the turn)
        remembered, full = _remember_self_facts(user_id, self_facts, conversation.id) if self_facts else ([], False)
        reply = social_reply(analysis, remembered, full, has_documents=bool(document_ids))
        yield "token", reply
        response, conversation = _save_turn(db, user_id, conversation, request.query, reply, [], False)
        yield "done", response
        return

    if not document_ids:
        reply, abstained = reply_without_documents(request.query)
        yield "token", reply
        response, conversation = _save_turn(db, user_id, conversation, request.query, reply, [], abstained)
        if self_facts:
            _remember_self_facts(user_id, self_facts, conversation.id)
        yield "done", response
        return

    retrieval = run_retrieval(
        request.query,
        user_id=user_id,
        llm=llm,
        history=_history_as_text(summary, history, memories),
        document_ids=document_ids,
    )

    generation = None
    try:
        for kind, value in stream_answer(request.query, llm, retrieval.chunks, history, summary, memories):
            if kind == "token":
                yield "token", value
            else:
                generation = value
    except Exception as error:
        logger.exception("LLM call failed")
        if looks_like_quota_error(error):
            raise HTTPException(
                status_code=429,
                detail="The AI service is busy or its free quota is used up. Please try again later.",
            )
        raise HTTPException(status_code=502, detail="The language model request failed, please try again")

    citations = [Citation(**asdict(citation)) for citation in generation.citations]
    response, conversation = _save_turn(db, user_id, conversation, request.query, generation.answer, citations, generation.abstained)
    if self_facts:
        _remember_self_facts(user_id, self_facts, conversation.id)
    yield "done", response

    # The answer is already saved and sent, so a problem here must never fail the request.
    # (If the client hung up after "done", this is skipped and tried again after the next question.)
    if _summarize_if_needed(db, conversation, llm):
        _remember_important_facts(user_id, conversation, llm)
    else:
        remember_if_due(db, user_id, conversation, llm)     # long chats: every few answers


@traceable(
    name="ask",
    process_inputs=lambda i: {"question": i["request"].query, "conversation_id": str(i["request"].conversation_id) if i["request"].conversation_id else None},
    process_outputs=lambda r: {
        "answer": r.answer, "abstained": r.abstained, "citations": len(r.citations),
        "conversation_id": str(r.conversation_id),
    },
)
def ask_question(db: Session, user_id: int, request: AskRequest, llm) -> AskResponse:
    """The whole turn at once (the JSON /ask endpoint): runs ask_stream and returns its final response."""
    response = None
    for kind, value in ask_stream(db, user_id, request, llm):
        if kind == "done":
            response = value
    return response
