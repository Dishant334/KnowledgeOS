"""
Long-term memory, learned once per conversation (an LLM call), on top of the instant self-facts
(services/introductions.py) and the summary-time update (services/ask._remember_important_facts).

The memory step (app/memory/consolidate.update_long_term_memory) gets the conversation's messages that were not
given to it yet, merges the durable facts (who the user is, preferences, ongoing projects; never secrets or document
content) into the user's ONE memory list, and the position is stored on the conversation
(`remembered_until_message_id`), so the same messages never cost a second call.

It runs:
  - when the user leaves a chat that got new answers (POST /conversations/{id}/remember, in the background);
  - inside /ask after an answer, when REMEMBER_EVERY_ANSWERS answers are waiting (long chats you never leave).
Greetings, small talk and refused or fixed replies are left out (the user's own words are kept even when the
answer was a refusal); if no user message is left, no LLM call is made.
A failure is logged and simply retried next time; it never fails a request.
"""

import logging

from sqlalchemy.orm import Session

from app.db.models.conversation import Conversation
from app.db.models.messages import Message
from app.generation.orchestrator import count_tokens
from app.generation.summary import format_messages
from app.memory.consolidate import update_long_term_memory

logger = logging.getLogger(__name__)

REMEMBER_EVERY_ANSWERS = 6     # the in-chat safety net for long chats
MAX_TOKENS = 1500              # the newest part of a very long stretch is enough to learn from


def _waiting(db: Session, conversation: Conversation) -> list[Message]:
    query = db.query(Message).filter_by(conversation_id=conversation.id)
    if conversation.remembered_until_message_id is not None:
        query = query.filter(Message.id > conversation.remembered_until_message_id)
    return query.order_by(Message.id).all()


def has_something_to_remember(db: Session, conversation: Conversation) -> bool:
    """True if the conversation has user messages that were not given to the memory step yet."""
    return any(m.role == "user" for m in _waiting(db, conversation))


def answers_waiting(db: Session, conversation: Conversation) -> int:
    return sum(1 for m in _waiting(db, conversation) if m.role == "assistant")


def _worth_learning_from(messages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    What the memory step sees: every real user message (even one whose answer was a refusal or "add a document
    first": what the user SAID can still matter), and only the real answers. Greetings / small talk (already
    handled instantly) and refused or fixed replies are left out.
    """
    from app.generation.orchestrator import is_refusal
    from app.services.introductions import analyze_message
    from app.services.small_talk import GREETING_REPLY, NEED_DOCUMENT_REPLY

    kept: list[tuple[str, str]] = []
    skip_answer = False
    for role, content in messages:
        if role == "user":
            skip_answer = analyze_message(content).only_social
            if not skip_answer:
                kept.append((role, content))
        elif not skip_answer and content not in (GREETING_REPLY, NEED_DOCUMENT_REPLY) and not is_refusal(content):
            kept.append((role, content))
    return kept


def remember_conversation(db: Session, user_id: int, conversation: Conversation, llm) -> bool:
    """Runs the memory step on the waiting messages. Returns True if the model was asked. Never raises."""
    try:
        messages = _waiting(db, conversation)
        if not messages:
            return False
        last_id = messages[-1].id
        useful = _worth_learning_from([(m.role, m.content) for m in messages])
        if not any(role == "user" for role, _ in useful):
            conversation.remembered_until_message_id = last_id   # only small talk / refusals: nothing to learn
            db.commit()
            return False

        kept, total = [], 0
        for role, content in reversed(useful):                     # the newest part, within the budget
            total += count_tokens(content)
            if kept and total > MAX_TOKENS:
                break
            kept.append((role, content))
        text = format_messages(list(reversed(kept)))

        update_long_term_memory(llm, user_id, text, conversation.id)
        conversation.remembered_until_message_id = last_id
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.warning("Could not update long-term memory from conversation %s; will retry later", conversation.id, exc_info=True)
        return False


def remember_if_due(db: Session, user_id: int, conversation: Conversation, llm) -> bool:
    """The in-chat safety net: run the memory step once REMEMBER_EVERY_ANSWERS answers are waiting."""
    if answers_waiting(db, conversation) >= REMEMBER_EVERY_ANSWERS:
        return remember_conversation(db, user_id, conversation, llm)
    return False
