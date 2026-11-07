"""
Replies for a chat that has NO documents attached (a question then has nothing to be answered from).

A greeting or other small talk ("hi", "thanks", "who are you") gets a friendly hello; anything else is asked to add a
document first. Decided with a fixed word list, not an LLM call: instant, free, and no quota is spent.
"""

import re

GREETING_REPLY = (
    "Hello! I'm KnowledgeOS. Add a document to this chat with the paperclip, and ask me anything about it: "
    "every answer points to the passage it came from."
)
NEED_DOCUMENT_REPLY = (
    "Please add a document to this chat first (use the paperclip), then ask your question. "
    "I only answer from the documents in this chat."
)

# whole messages that count as small talk (after lower-casing and dropping punctuation and emoji)
_SMALL_TALK = re.compile(
    r"^(?:"
    r"h+i+|hey+|hello+|hiya|yo|sup|what'?s up|howdy|namaste|"
    r"good (?:morning|afternoon|evening|night|day)|"
    r"how are (?:you|u)(?: doing)?(?: today)?|how'?s it going|"
    r"thanks?(?: you)?(?: (?:so|very) much)?|thank u|thx|ty|cheers|"
    r"ok(?:ay)?|cool|nice|great|bye|goodbye|see you|"
    r"who are you|what are you|what can you do|help"
    r")(?: (?:there|again|kos|knowledgeos|bot))?$"
)


def is_small_talk(text: str) -> bool:
    cleaned = re.sub(r"[^a-z' ]+", " ", text.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return bool(cleaned) and len(cleaned) <= 40 and bool(_SMALL_TALK.match(cleaned))


def reply_without_documents(text: str) -> tuple[str, bool]:
    """(reply, abstained) for a question asked in a chat without documents."""
    if is_small_talk(text):
        return GREETING_REPLY, False
    return NEED_DOCUMENT_REPLY, True
