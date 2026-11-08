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

# Tuned with the local Qwen3 8B (2026-11-09): the earlier wording ("return the updated list") made it answer [] for a
# user who said "I'm preparing the onboarding guide"; this one keeps known facts, adds what the USER says about
# themselves, replaces a fact the user changes ("I moved to the Munich office"), and leaves out document facts,
# questions and secrets (5 cases x 2 runs checked).
MEMORY_PROMPT = ChatPromptTemplate.from_template(
    """You maintain the long-term memory of an assistant that answers questions about a user's documents.
Below are the facts already remembered about the user and a recent conversation (its summary or its messages).
Return the COMPLETE updated list of facts about the user, for FUTURE conversations:
1. Start with every fact remembered so far. Keep each one, EXCEPT when the user now says something different: then REPLACE the old fact with the new one.
   For example, remembered "Works in the Berlin office" + the user says "I moved to the Munich office" -> keep only "Works in the Munich office".
2. Add each NEW durable fact the USER states about THEMSELVES in their own messages: who they are (name, role, team, office, company name), what they are working on (projects, goals, tasks they are preparing), and their preferences (language, level of detail, format).
   For example "I'm preparing the onboarding guide for new employees" becomes "Is preparing the onboarding guide for new employees".
Never add: what the user asked about (questions are not facts), anything taken from the assistant's answers or from the documents (prices, numbers, policies, rules), guesses or vague facts the user did not say, passwords or ID numbers, health or financial details, or anything about other people.
Merge duplicates, keep each fact under 25 words and at most {max_items} facts.
Return ONLY a JSON list of strings, for example ["Name: Asha", "Works in the Berlin office", "Prefers short answers"]. If nothing changed, return the facts remembered so far unchanged.

Remembered so far:
{memories}

The recent conversation:
{summary}

Updated JSON list:"""
)

# "Asks about the parking fee" is a question, not a fact; an 8B model still writes such lines now and then.
NOT_A_FACT = re.compile(r"^(?:asks?|asked|is asking|wants? to know|wanted to know|inquir\w*|wonder\w*)\b|^works at a company\.?$", re.I)


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
    updated = [text for text in updated if not NOT_A_FACT.search(text.strip())]

    # A name the user told us is kept unless the model returns a (new) name itself: models often drop it.
    names = [text for text in existing if text.lower().startswith("name:")]
    if names and not any(text.lower().startswith("name:") for text in updated):
        updated = names[:1] + updated

    if not updated and existing:
        # An empty list almost always means "nothing new", not "forget everything".
        # Deleting memories is the user's decision (DELETE /memory).
        logger.info("Memory update returned an empty list; keeping the %d existing facts", len(existing))
        return len(existing)

    replace_memories(user_id, updated, conversation_id)
    return len(list_memories(user_id))
