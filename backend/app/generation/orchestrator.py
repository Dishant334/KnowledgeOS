# app/generation/orchestrator.py

import logging
import re
from functools import lru_cache

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.augmentation.model import Citation
from app.retrieval.model import ScoredChunk
from app.augmentation.context_builder import ContextBuilder
from app.generation.chain import build_generation_chain
from app.generation.models import GenerationResult

logger = logging.getLogger(__name__)

# Most history we send to the model. Context (3000) + history + question + the
# answer itself must all fit in the model's window (8192 tokens for local Qwen).
HISTORY_MAX_TOKENS = 1500

NO_ANSWER = "I don't have enough information to answer that."

# Ways a model says "the context doesn't answer this" (checked in lowercase,
# after turning typographic apostrophes into plain ones)
REFUSAL_PHRASES = (
    "don't have enough information",
    "do not have enough information",
    "not enough information",
    "does not contain enough information",
    "doesn't contain enough information",
    "does not provide enough information",
    "doesn't provide enough information",
    "insufficient information",
)

# Matches "[1]", "[12]" and also "[1, 2]"
CITATION_GROUP = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


@lru_cache(maxsize=1)
def get_context_builder() -> ContextBuilder:
    """Created on first use, so importing this module does no work (the tokenizer loads lazily)."""
    return ContextBuilder()


def trim_history(
    history: list[tuple[str, str]],
    max_tokens: int = HISTORY_MAX_TOKENS,
) -> list[tuple[str, str]]:
    """
    Keeps the most recent messages that fit in max_tokens; the oldest are dropped.
    The result always starts with a user message (some providers, e.g. Gemini,
    reject a conversation that starts with the assistant).
    """
    encoding = get_context_builder().encoding

    kept = []
    total = 0
    for role, content in reversed(history):
        tokens = len(encoding.encode(content))
        if total + tokens > max_tokens:
            break
        kept.append((role, content))
        total += tokens
    kept.reverse()

    while kept and kept[0][0] != "user":
        kept.pop(0)
    return kept


def to_chat_messages(history: list[tuple[str, str]]) -> list[BaseMessage]:
    """[("user", "hi"), ("assistant", "hello")] -> LangChain messages."""
    messages = []
    for role, content in history:
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    return messages


def cited_numbers(answer: str) -> set[int]:
    """The citation numbers used in an answer: "A [1] and B [2, 3]" -> {1, 2, 3}."""
    numbers = set()
    for group in CITATION_GROUP.findall(answer):
        for number in group.split(","):
            numbers.add(int(number))
    return numbers


def is_refusal(answer: str) -> bool:
    """
    True if the answer says the context doesn't contain the answer.
    An answer that cites a source is a real answer, even if it mentions
    "not enough information" about some other detail.
    """
    if cited_numbers(answer):
        return False

    text = answer.lower().replace("’", "'")  # curly apostrophe -> '
    return any(phrase in text for phrase in REFUSAL_PHRASES)


def only_cited(citations: list[Citation], answer: str) -> list[Citation]:
    """
    Keep just the sources the answer refers to. If the answer cites nothing
    (or only numbers that don't exist), keep all of them so the user can
    still see where the information came from.
    """
    numbers = cited_numbers(answer)
    used = [c for c in citations if int(c.marker.strip("[]")) in numbers]
    return used or citations


def no_answer() -> GenerationResult:
    return GenerationResult(answer=NO_ANSWER, citations=[], abstained=True)


def generate_answer(
    question: str,
    llm,
    chunks: list[ScoredChunk],
    history: list[tuple[str, str]] | None = None,
) -> GenerationResult:
    """
    Builds the cited context from the retrieved chunks and asks the LLM to
    answer ONLY from it. If there is nothing to answer from, the LLM is not
    called at all (it could only guess).
    """
    if not chunks:
        return no_answer()

    augmented = get_context_builder().build(chunks)
    if augmented.chunks_used == 0:
        logger.warning("All %d retrieved chunks are bigger than the context budget", len(chunks))
        return no_answer()

    chain = build_generation_chain(llm)
    answer = chain.invoke(
        {
            "context": augmented.prompt_context,
            "question": question,
            "history": to_chat_messages(history or []),
        }
    )

    if not answer.strip():
        logger.warning("The model returned an empty answer")
        return no_answer()

    if is_refusal(answer):
        return GenerationResult(answer=answer, citations=[], abstained=True)

    return GenerationResult(
        answer=answer,
        citations=only_cited(augmented.citations, answer),
        abstained=False,
    )
