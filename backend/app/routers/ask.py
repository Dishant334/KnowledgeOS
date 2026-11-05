import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.db.database import get_db
from app.db.models.user import User
from app.core.rate_limit import limit_ask
from app.generation.llm import get_llm
from app.schemas.ask import AskRequest, AskResponse
from app.services.ask import ask_question, ask_stream

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/ask", response_model=AskResponse, dependencies=[Depends(limit_ask)])
def ask(
    request: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm=Depends(get_llm),
):
    if llm is None:
        raise HTTPException(status_code=503, detail="No LLM is configured on the server yet")

    try:
        return ask_question(db, user_id=current_user.id, request=request, llm=llm)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


def sse_event(event: str, data: dict) -> str:
    """One Server-Sent Event. The data is JSON on a single line, so newlines in the answer cannot break the framing."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/ask/stream", dependencies=[Depends(limit_ask)])
def ask_streaming(
    request: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm=Depends(get_llm),
):
    """
    Same as /ask, but the answer arrives as Server-Sent Events while the model writes it:

        event: token   data: {"text": "..."}          (many)
        event: done    data: <the /ask JSON response> (once; its "answer" is the one to trust)
        event: error   data: {"status": 502, "detail": "..."}   (only if it breaks after the stream began)
    """
    if llm is None:
        raise HTTPException(status_code=503, detail="No LLM is configured on the server yet")

    events = ask_stream(db, user_id=current_user.id, request=request, llm=llm)

    # Run retrieval and wait for the first token BEFORE answering. Problems up to here (unknown
    # conversation, quota, LLM down) are still returned as proper HTTP errors, not as a 200 stream.
    try:
        first = next(events)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

    def stream():
        try:
            yield to_sse(first)
            for event in events:
                yield to_sse(event)
        except HTTPException as e:
            yield sse_event("error", {"status": e.status_code, "detail": e.detail})
        except Exception:
            logger.exception("Streaming /ask failed")
            yield sse_event("error", {"status": 500, "detail": "Something went wrong, please try again"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},   # no proxy buffering
    )


def to_sse(event: tuple[str, object]) -> str:
    kind, value = event
    if kind == "token":
        return sse_event("token", {"text": value})
    return sse_event("done", json.loads(AskResponse.model_validate(value).model_dump_json()))
