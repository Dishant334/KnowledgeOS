import logging

from fastapi import HTTPException

from app.memory import store
from app.schemas.memory import MemoryOut

logger = logging.getLogger(__name__)


def _to_out(memory: store.Memory) -> MemoryOut:
    return MemoryOut(
        id=memory.key,
        text=memory.text,
        created_at=memory.created_at,
        source_conversation_id=memory.source_conversation_id,
    )


def _unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="Memory is temporarily unavailable, please try again")


def list_user_memories(user_id: int) -> list[MemoryOut]:
    try:
        return [_to_out(memory) for memory in store.list_memories(user_id)]
    except Exception:
        logger.exception("Could not list memories")
        raise _unavailable()


def create_user_memory(user_id: int, text: str) -> MemoryOut:
    try:
        return _to_out(store.add_memory(user_id, text))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except store.MemoryLimitError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except Exception:
        logger.exception("Could not save memory")
        raise _unavailable()


def delete_user_memory(user_id: int, memory_id: str) -> None:
    try:
        deleted = store.delete_memory(user_id, memory_id)
    except Exception:
        logger.exception("Could not delete memory")
        raise _unavailable()

    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")


def delete_all_user_memories(user_id: int) -> None:
    try:
        store.delete_all_memories(user_id)
    except Exception:
        logger.exception("Could not delete memories")
        raise _unavailable()
