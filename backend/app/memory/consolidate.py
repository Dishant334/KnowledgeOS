# app/memory/consolidate.py
#
# Turns "what we already remember" + "the summary of a conversation" into the
# updated list of facts worth remembering for FUTURE conversations.

import json
import logging
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.memory.store import MAX_MEMORIES_PER_USER, list_memories, replace_memories

logger = logging.getLogger(__name__)

MEMORY_PROMPT = ChatPromptTemplate.from_template(
    """You maintain the long-term memory of an assistant that answers questions about a user's documents.
Below are the facts already remembered about the user and a summary of a recent conversation.
Return the updated list of facts worth remembering for FUTURE conversations.

Remember only what stays true and useful: who the user is (role, team, office), their preferences (language, level of detail), their ongoing projects or goals, and decisions they made.
Do NOT remember: facts that are in the documents (they can be searched again), one-off questions, passwords or ID numbers, health or financial details, or anything about other people.
Merge duplicates, drop facts the conversation contradicts, and keep each fact under 25 words and at most {max_items} facts.
Return ONLY a JSON list of strings, for example ["Works in the Berlin office", "Prefers short answers"]. Return [] if there is nothing to remember.

Remembered so far:
{memories}

Summary of the recent conversation:
{summary}

Updated JSON list:"""
)


def parse_memory_list(raw: str) -> list[str] | None:
    """
    The model's answer as a list of strings, or None if it is not a JSON list of strings
    (models sometimes wrap it in ```json fences or add a sentence around it).
    """
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return None
    if "{" in raw[:start]:
        return None  # a JSON object that merely contains a list: ambiguous, so not accepted
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return None

    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        return None
    return data


def update_long_term_memory(llm, user_id: int, conversation_summary: str, conversation_id: int | None) -> int:
    """
    Merges the important parts of a conversation summary into the user's long-term
    memory. Returns how many facts the user has afterwards.
    Raises ValueError if the model's answer is unusable, so the old memory stays untouched.
    """
    existing = [memory.text for memory in list_memories(user_id)]

    raw = (MEMORY_PROMPT | llm | StrOutputParser()).invoke(
        {
            "max_items": MAX_MEMORIES_PER_USER,
            "memories": "\n".join(f"- {text}" for text in existing) or "(nothing yet)",
            "summary": conversation_summary,
        }
    )

    updated = parse_memory_list(raw)
    if updated is None:
        raise ValueError("The model did not return a JSON list of facts")

    if not updated and existing:
        # An empty list almost always means "nothing new", not "forget everything".
        # Deleting memories is the user's decision (DELETE /memory).
        logger.info("Memory update returned an empty list; keeping the %d existing facts", len(existing))
        return len(existing)

    replace_memories(user_id, updated, conversation_id)
    return len(list_memories(user_id))
