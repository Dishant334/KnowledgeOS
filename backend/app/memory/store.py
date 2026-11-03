# app/memory/store.py
#
# Long-term memory: short facts about a user that are remembered across ALL of
# their conversations. Stored with LangGraph's PostgresStore (the store LangChain
# recommends for long-term memory) in our own Postgres database.
#
# Layout: namespace ("user_memory", "<user id>") -> one item per fact,
#         value = {"text": "...", "source_conversation_id": 12 or None}
# The namespace is what keeps users apart: every function takes a user_id and
# only ever touches that user's namespace.

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from langgraph.store.postgres import PostgresStore
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

NAMESPACE_ROOT = "user_memory"

# Small on purpose: every remembered fact is sent with every question.
MAX_MEMORIES_PER_USER = 15
MAX_MEMORY_CHARS = 200

# Things we never keep: secrets / ID-like numbers, and text that tries to give the
# assistant orders (memory is shown to the model, so it must not become a way to
# smuggle instructions into every future prompt).
SENSITIVE = re.compile(
    r"password|passcode|api[ _-]?key|secret|token|credit card|\bssn\b|social security|\d{9,}",
    re.IGNORECASE,
)
INSTRUCTION_LIKE = re.compile(
    r"ignore (all |any |the )?(previous|prior|above)|disregard|system prompt|you must|always answer|never answer",
    re.IGNORECASE,
)


class MemoryLimitError(Exception):
    """The user already has MAX_MEMORIES_PER_USER facts."""


@dataclass
class Memory:
    key: str
    text: str
    created_at: datetime
    source_conversation_id: int | None = None


def clean_memory_text(text: str) -> str | None:
    """
    The fact as it will be stored, or None if it must not be stored
    (empty, sensitive, or written like an instruction).
    """
    text = " ".join(text.split())[:MAX_MEMORY_CHARS]
    if not text or SENSITIVE.search(text) or INSTRUCTION_LIKE.search(text):
        return None
    return text


@lru_cache(maxsize=1)
def get_memory_store() -> PostgresStore:
    """
    Connects on first use (not at import) and creates the store's tables if they
    are missing. Reused afterwards.
    """
    pool = ConnectionPool(
        conninfo=settings.database_url,
        max_size=5,
        # what PostgresStore needs: autocommit, no prepared statements, dict rows
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    pool.open(wait=True, timeout=10)  # raises if the database is unreachable

    store = PostgresStore(pool)
    store.setup()  # idempotent
    return store


def close_memory_store() -> None:
    """Closes the connection pool if the store was ever used (called when the app shuts down)."""
    if get_memory_store.cache_info().currsize:
        get_memory_store().conn.close()
        get_memory_store.cache_clear()


def _namespace(user_id: int) -> tuple[str, str]:
    return (NAMESPACE_ROOT, str(user_id))


def _to_memory(item) -> Memory:
    return Memory(
        key=item.key,
        text=item.value["text"],
        created_at=item.created_at,
        source_conversation_id=item.value.get("source_conversation_id"),
    )


def list_memories(user_id: int) -> list[Memory]:
    """All remembered facts of this user, oldest first."""
    items = get_memory_store().search(_namespace(user_id), limit=MAX_MEMORIES_PER_USER + 100)
    return sorted((_to_memory(item) for item in items), key=lambda memory: memory.created_at)


def add_memory(user_id: int, text: str, conversation_id: int | None = None) -> Memory:
    """
    Stores one fact. Raises ValueError if the text is not allowed (see clean_memory_text)
    and MemoryLimitError if the user already has the maximum.
    """
    cleaned = clean_memory_text(text)
    if cleaned is None:
        raise ValueError("This text is empty, looks sensitive, or looks like an instruction")
    if len(list_memories(user_id)) >= MAX_MEMORIES_PER_USER:
        raise MemoryLimitError(f"You can keep at most {MAX_MEMORIES_PER_USER} memories")

    key = uuid.uuid4().hex
    store = get_memory_store()
    store.put(_namespace(user_id), key, {"text": cleaned, "source_conversation_id": conversation_id})
    return _to_memory(store.get(_namespace(user_id), key))


def delete_memory(user_id: int, key: str) -> bool:
    """Deletes one fact of this user. False if there is no such fact (or it belongs to someone else)."""
    store = get_memory_store()
    if store.get(_namespace(user_id), key) is None:
        return False
    store.delete(_namespace(user_id), key)
    return True


def delete_all_memories(user_id: int) -> int:
    """Forgets everything about this user. Returns how many facts were deleted."""
    store = get_memory_store()
    items = store.search(_namespace(user_id), limit=1000)
    for item in items:
        store.delete(_namespace(user_id), item.key)
    return len(items)


def replace_memories(user_id: int, texts: list[str], conversation_id: int | None = None) -> None:
    """
    Makes the user's memories equal to `texts`, touching as little as possible:
    unchanged facts keep their item (and creation date), missing ones are deleted,
    new ones are added. Texts that are not allowed are skipped.
    """
    wanted = []
    for text in texts:
        cleaned = clean_memory_text(text)
        if cleaned and cleaned.lower() not in [w.lower() for w in wanted]:
            wanted.append(cleaned)
    wanted = wanted[:MAX_MEMORIES_PER_USER]

    store = get_memory_store()
    existing = {memory.text.lower(): memory for memory in list_memories(user_id)}

    for text_lower, memory in existing.items():
        if text_lower not in [w.lower() for w in wanted]:
            store.delete(_namespace(user_id), memory.key)

    for text in wanted:
        if text.lower() not in existing:
            store.put(
                _namespace(user_id),
                uuid.uuid4().hex,
                {"text": text, "source_conversation_id": conversation_id},
            )
