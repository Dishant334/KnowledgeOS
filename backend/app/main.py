from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from app.routers.auth import router as auth_router
from app.routers.document import router as document_router
from app.routers.retrieve import router as retrieve_router
from app.routers.ask import router as ask_router
from app.routers.memory import router as memory_router
from app.db.database import engine
from app.memory.store import close_memory_store


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # shutdown: close the long-term memory connection pool (only if it was ever opened)
    close_memory_store()


app = FastAPI(title="KnowledgeOS", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/test-db")
def test_db():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {"status": "connected"}

    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
        }


app.include_router(auth_router)
app.include_router(document_router)
app.include_router(retrieve_router)
app.include_router(ask_router)
app.include_router(memory_router)
