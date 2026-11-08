"""
Replies for a chat that has NO documents attached when the question is a real question (not small talk):
it is asked to add a document first. Greetings and small talk are answered by services/introductions.py
(any chat, no LLM call); `is_small_talk` and `GREETING_REPLY` are kept here for older callers.
"""

from app.services.introductions import GREETING_REPLY, analyze_message  # noqa: F401  (re-exported)

NEED_DOCUMENT_REPLY = (
    "Please add a document to this chat first (use the paperclip), then ask your question. "
    "I only answer from the documents in this chat."
)


def is_small_talk(text: str) -> bool:
    """True when the whole message is greetings / small talk (no real question and no self-fact)."""
    analysis = analyze_message(text)
    return analysis.only_social and not analysis.facts


def reply_without_documents(text: str) -> tuple[str, bool]:
    """(reply, abstained) for a real question asked in a chat without documents."""
    if is_small_talk(text):
        return GREETING_REPLY, False
    return NEED_DOCUMENT_REPLY, True
