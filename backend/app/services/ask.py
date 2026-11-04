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
    stream_answer,
    trim_history,
)
from app.generation.summary import format_messages, split_for_summary, summarize
from app.memory.consolidate import update_long_term_memory
from app.memory.store import list_memories
from app.schemas.ask import AskRequest, AskResponse, Citation
from app.services.retrieve import run_retrieval

logger = logging.getLogger(__name__)


def looks_like_quota_error(error: Exception) -> bool:
    """
    True if an LLM error means "too many requests / free quota used up".
    Every provider SDK raises its own exception type, so we look at the text.
    """
    text = f"{type(error).__name__} {error}".lower()
    words = ("429", "quota", "rate limit", "rate_limit", "ratelimit", "resource_exhausted", "too many requests")
    return any(word in text for word in words)


def _get_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter_by(id=conversation_id, user_id=user_id)
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


def ask_stream(db: Session, user_id: int, request: AskRequest, llm) -> Iterator[tuple[str, object]]:
    """
    retrieve -> build cited context -> generate answer -> save the turn, as a stream of events:

        ("token", "text piece") ...   the answer as the model writes it
        ("done", AskResponse)         once, after the turn is saved (the answer in it is the one to trust)

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
        history = trim_history(unsummarized)  # safety net only: normally already small thanks to the summary

    retrieval = run_retrieval(
        request.query,
        user_id=user_id,
        llm=llm,
        history=_history_as_text(summary, history, memories),
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

    if conversation is None:
        conversation = Conversation(user_id=user_id, title=request.query[:80])
        db.add(conversation)
        db.flush()  # gives the conversation an id

    if conversation.title is None:
        # a chat started with "New chat" has no title yet: the first question names it
        # (a title given at creation, or set by renaming, is never replaced)
        conversation.title = request.query[:80]

    citations = [Citation(**asdict(citation)) for citation in generation.citations]

    db.add(Message(conversation_id=conversation.id, role="user", content=request.query))
    # The citations are saved with the answer (same shape as in the response), so the conversation
    # can be shown again later, source cards included.
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=generation.answer,
        citations=[citation.model_dump() for citation in citations],
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    response = AskResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=generation.answer,
        citations=citations,
        abstained=generation.abstained,
        created_at=assistant_message.created_at,
    )
    yield "done", response

    # The answer is already saved and sent, so a problem here must never fail the request.
    # (If the client hung up after "done", this is skipped and tried again after the next question.)
    if _summarize_if_needed(db, conversation, llm):
        _remember_important_facts(user_id, conversation, llm)


@traceable(
    name="ask",
    process_inputs=lambda i: {"question": i["request"].query, "conversation_id": i["request"].conversation_id},
    process_outputs=lambda r: {
        "answer": r.answer, "abstained": r.abstained, "citations": len(r.citations),
        "conversation_id": r.conversation_id,
    },
)
def ask_question(db: Session, user_id: int, request: AskRequest, llm) -> AskResponse:
    """The whole turn at once (the JSON /ask endpoint): runs ask_stream and returns its final response."""
    response = None
    for kind, value in ask_stream(db, user_id, request, llm):
        if kind == "done":
            response = value
    return response
