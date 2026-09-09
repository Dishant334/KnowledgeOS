# app/generation/memory.py

import uuid
import logging

from langchain_postgres import PostgresChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
import psycopg

from app.core.config import settings

logger = logging.getLogger(__name__)

TABLE_NAME = "message_store"


def _get_psycopg_dsn() -> str:
    """
    psycopg (v3) needs a plain "postgresql://..." DSN. settings.database_url
    is already in that form for a plain create_engine() setup (no
    "+driver" suffix like "+asyncpg" to strip, since app/db/database.py
    uses sync create_engine directly) — reused as-is rather than
    duplicating the connection string in a second place.
    """
    return settings.database_url


# One shared sync connection, built from the same config the rest of
# the app uses — not a second, independently-configured connection.
_sync_connection = psycopg.connect(_get_psycopg_dsn())


def ensure_message_table() -> None:
    """
    Creates the table PostgresChatMessageHistory expects, if it
    doesn't already exist. Call once at app startup (see main.py).
    Idempotent — safe to call on every boot.
    """
    PostgresChatMessageHistory.create_tables(_sync_connection, TABLE_NAME)


def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """
    Returns the chat history for one conversation (session_id).
    This is the SINGLE source of truth for conversation history —
    used by generation (RunnableWithMessageHistory) AND by retrieval
    (query rewriting), so both stages see the same conversation state.
    """
    return PostgresChatMessageHistory(
        TABLE_NAME,
        session_id,
        sync_connection=_sync_connection,
    )


def get_formatted_history(session_id: str, max_turns: int = 5) -> str:
    """
    Reads the last `max_turns` messages from Postgres and formats them
    as a plain string, for use anywhere a text-based history is needed
    (currently: query_rewriter.py's prompt). Capped at max_turns since
    query rewriting only needs recent context, not the full conversation.
    """
    history = get_session_history(session_id)
    messages = history.messages[-max_turns * 2:]  # *2: each turn is a human+ai pair

    if not messages:
        return ""

    lines = []
    for message in messages:
        role = "User" if message.type == "human" else "Assistant"
        lines.append(f"{role}: {message.content}")

    return "\n".join(lines)


def new_session_id() -> str:
    return str(uuid.uuid4())


def wrap_with_history(chain):
    from langchain_core.runnables.history import RunnableWithMessageHistory
    return RunnableWithMessageHistory(
        chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="history",
    )