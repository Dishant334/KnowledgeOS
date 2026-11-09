"""
The reply for a REAL question asked in a chat that has no documents: it is asked to add a document first.
Greetings and small talk never get here: services/introductions.py answers them earlier (any chat, no LLM call).
`GREETING_REPLY` is re-exported for the callers that filter fixed replies out of the history.
"""

from app.services.introductions import GREETING_REPLY  # noqa: F401  (re-exported)

NEED_DOCUMENT_REPLY = (
    "Please add a document to this chat first (use the paperclip), then ask your question. "
    "I only answer from the documents in this chat."
)


def reply_without_documents(text: str) -> tuple[str, bool]:
    """(reply, abstained) for a real question asked in a chat without documents."""
    return NEED_DOCUMENT_REPLY, True
