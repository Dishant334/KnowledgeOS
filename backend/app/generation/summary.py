# app/generation/summary.py
#
# Long conversations: instead of throwing the oldest messages away, they are
# folded into a short rolling summary. The messages stay in the database; only
# the prompt uses the summary (plus the most recent messages as they are).

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.generation.orchestrator import count_tokens

SUMMARY_MAX_WORDS = 150

SUMMARY_PROMPT = ChatPromptTemplate.from_template(
    """Update the running summary of a conversation between a user and an assistant that answers questions about the user's documents.

Keep: what the user asked, the key facts and numbers in the answers, names of people and documents, and anything the user said about themselves or what they want. Leave out greetings and filler.
Write at most {max_words} words of plain text. Return ONLY the new summary.

Current summary (may be empty):
{summary}

New messages:
{messages}

New summary:"""
)


def format_messages(messages: list[tuple[str, str]]) -> str:
    """[("user", "hi"), ("assistant", "hello")] -> "User: hi\\nAssistant: hello"."""
    lines = []
    for role, content in messages:
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def summarize(llm, previous_summary: str, messages: list[tuple[str, str]]) -> str:
    """
    Returns the previous summary updated with these messages.
    Raises ValueError if the model returns nothing, so the caller keeps the old summary.
    """
    chain = SUMMARY_PROMPT | llm | StrOutputParser()
    new_summary = chain.invoke(
        {
            "max_words": SUMMARY_MAX_WORDS,
            "summary": previous_summary or "(none yet)",
            "messages": format_messages(messages),
        }
    ).strip()

    if not new_summary:
        raise ValueError("The model returned an empty summary")
    return new_summary


def split_for_summary(
    messages: list[tuple[int, str, str]],
    keep_tokens: int,
) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
    """
    messages are (id, role, content), oldest first.
    Returns (old, recent): `recent` is the newest tail that fits in keep_tokens
    and starts with a user message; `old` is everything before it (to be summarized).
    """
    recent = []
    total = 0
    for message in reversed(messages):
        tokens = count_tokens(message[2])
        if total + tokens > keep_tokens:
            break
        recent.append(message)
        total += tokens
    recent.reverse()

    while recent and recent[0][1] != "user":
        recent.pop(0)

    old = messages[: len(messages) - len(recent)]
    return old, recent
