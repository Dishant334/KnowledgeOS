from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.auth import router as auth_router
from app.routers.document import router as document_router
from app.routers.retrieve import router as retrieve_router
from app.routers.ask import router as ask_router
from app.routers.memory import router as memory_router
from app.routers.conversations import router as conversations_router
from app.core.config import settings
from app.core.cors import cors_options
from app.memory.store import close_memory_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # shutdown: close the long-term memory connection pool (only if it was ever opened)
    close_memory_store()


app = FastAPI(title="KnowledgeOS", lifespan=lifespan)

# Lets the browser frontend call the API (see app/core/cors.py). Added before the routes; it answers the
# browser's preflight requests itself, so they never reach authentication.
_cors = cors_options(settings.cors_origins)
if _cors:
    app.add_middleware(CORSMiddleware, **_cors)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(document_router)
app.include_router(retrieve_router)
app.include_router(ask_router)
app.include_router(memory_router)
app.include_router(conversations_router)
